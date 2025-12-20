// registros/static/js/registros.js
(function () {
  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  // =========================
  // Filtros
  // =========================
  const frm        = $("#frmFiltros");
  const inpBusca   = $("#f_busca");

  // ⚠️ compat: pode ser <select> (legado) OU <input> (autocomplete)
  const selProf    = $("#f_prof");         // SELECT ou INPUT
  const inpProfId  = $("#f_prof_id");      // hidden (novo)
  const sugBox     = $("#f_prof_sugestoes");// container (novo)

  const inpDataIni = $("#f_data_ini");
  const inpDataFim = $("#f_data_fim");
  const selStatus  = $("#f_status");
  const selSexo    = $("#f_sexo");
  const inpCID     = $("#f_cid");
  const inpCidade  = $("#f_cidade");

  const btnFiltrar        = $("#btnFiltrar");
  const btnLimpar         = $("#btnLimpar");
  const btnExportar       = $("#btnExportar");        // XLSX
  const btnExportarEvoPdf = $("#btnExportarEvoPdf");  // PDF evoluções ✅

  // =========================
  // Tabela
  // =========================
  const tbl       = $("#tblRegistros");
  const tbody     = $("#tblRegistros tbody");
  const lblResumo = $("#lblResumo");

  // =========================
  // Paginação
  // =========================
  const pagInfo     = $("#pagInfo");
  const pagAtualEl  = $("#pagAtual");
  const pagTotalEl  = $("#pagTotal");
  const btnPagFirst = $("#pagFirst");
  const btnPagPrev  = $("#pagPrev");
  const btnPagNext  = $("#pagNext");
  const btnPagLast  = $("#pagLast");

  const PAGE_SIZE = 15;
  let allRows     = [];
  let currentPage = 1;

  // =========================
  // Modal externo
  // =========================
  const dlg = $("#modal-registro");

  // header “novo”
  const mrSubtitle    = $("#mr_subtitle");
  const mrBadgeData   = $("#mr_badge_data");
  const mrBadgeStatus = $("#mr_badge_status");
  const mrBadgeCbo    = $("#mr_badge_cbo");
  const mrBtnCopyEvo  = $("#mr_btn_copiar_evo");

  // atendimento
  const mrProf         = $("#mr_profissional");
  const mrProfCns      = $("#mr_prof_cns");
  const mrProfCbo      = $("#mr_prof_cbo");
  const mrProcedimento = $("#mr_procedimento");
  const mrSigtap       = $("#mr_sigtap");
  const mrCid          = $("#mr_cid");
  const mrData         = $("#mr_data");
  const mrStatus       = $("#mr_status");
  const mrStatusJust   = $("#mr_status_just");
  const mrEvolucao     = $("#mr_evolucao");
  const mrKV           = $("#mr_kv");

  // paciente (aba paciente)
  const mrPaciente    = $("#mr_paciente");
  const mrProntuario  = $("#mr_prontuario");
  const mrPacIdade    = $("#mr_paciente_idade");
  const mrPacMod      = $("#mr_paciente_mod");
  const mrPacCPF      = $("#mr_pac_cpf");
  const mrPacCNS      = $("#mr_pac_cns");
  const mrPacNasc     = $("#mr_pac_nasc");
  const mrPacSexo     = $("#mr_pac_sexo");
  const mrPacTel      = $("#mr_pac_tel");
  const mrPacCidade   = $("#mr_pac_cidade");
  const mrPacEndereco = $("#mr_pac_endereco");

  // Guarda o último registro aberto no modal (pra exportar PDF por paciente)
  let lastModalRowObj = null;

  // Fallback estático (se o endpoint de profissionais falhar)
  const PROFISSIONAIS = {
    "101": "Dr. João (Clínico)",
    "102": "Dra. Maria (Psicologia)",
    "103": "Fisio Pedro (Fisioterapia)",
  };

  // =========================
  // Helpers
  // =========================
  const safe = (v, alt = "—") => (v === undefined || v === null || v === "" ? alt : v);

  function valFiltro(v) {
    if (v == null) return "";
    const s = String(v).trim();
    if (!s) return "";
    const low = s.toLowerCase();
    if (low === "todos" || low === "todo" || low === "-" || low === "*") return "";
    return s;
  }

  const fmtDataBR = (d) => {
    if (!d) return "—";
    const s = String(d);
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      const [y, m, dia] = s.split("-");
      return `${dia}/${m}/${y}`;
    }
    // tenta ISO datetime: 2025-12-18 10:00 / 2025-12-18T10:00
    if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(s)) {
      const y = s.slice(0, 4), m = s.slice(5, 7), dia = s.slice(8, 10);
      return `${dia}/${m}/${y}`;
    }
    return s;
  };

  function pick(obj, keys, fallback = "—") {
    for (const k of keys) {
      if (k in obj && obj[k] != null && obj[k] !== "") return obj[k];
    }
    return fallback;
  }

  function setText(el, value, fallback = "—") {
    if (!el) return;
    const v = value === undefined || value === null || String(value).trim() === "" ? fallback : value;
    el.textContent = String(v);
  }

  function mapFill(obj, mapping) {
    mapping.forEach((m) => {
      const raw = pick(obj, m.keys, m.fallback ?? "—");
      const val = typeof m.fmt === "function" ? m.fmt(raw, obj) : raw;
      setText(m.el, val, m.fallback ?? "—");
    });
  }

  function profNameFrom(obj) {
    const direct = pick(
      obj,
      ["profissional_nome", "profissional", "nome_profissional", "usuario_nome", "nome_usuario"],
      ""
    );
    if (direct) return direct;

    const pid =
      obj["profissional_id"] ??
      obj["prof_id"] ??
      obj["id_profissional"] ??
      obj["usuario_id"] ??
      "";

    if (pid && String(pid) in PROFISSIONAIS) return PROFISSIONAIS[String(pid)];
    return pid ? `ID ${pid}` : "—";
  }

  function normalizeStatusLabel(s) {
    const v = String(s || "").trim();
    if (!v) return "—";
    const low = v.toLowerCase();

    if (low.includes("pres") || low === "ok" || low === "compareceu") return "Presente";
    if (low.includes("falta") || low.includes("falt") || low === "nao compareceu") return "Faltoso";
    if (low.includes("just")) return "Justificado";

    return v;
  }

  function statusEmoji(label) {
    const low = String(label || "").toLowerCase();
    if (low.includes("presente")) return "✅";
    if (low.includes("just")) return "🟣";
    if (low.includes("falt")) return "❌";
    return "ℹ️";
  }

  function formatTelefones(obj) {
    const tels = [];
    const t1 = pick(obj, ["paciente_telefone1", "telefone1", "telefone", "telefone_paciente"], "");
    const t2 = pick(obj, ["paciente_telefone2", "telefone2"], "");
    const t3 = pick(obj, ["paciente_telefone3", "telefone3", "celular", "celular_paciente"], "");
    [t1, t2, t3].forEach((t) => {
      const st = String(t || "").trim();
      if (st) tels.push(st);
    });
    return tels.length ? tels.join(" • ") : "—";
  }

  function formatEndereco(obj) {
    const lograd  = pick(obj, ["paciente_logradouro", "logradouro", "rua"], "");
    const num     = pick(obj, ["paciente_numero_casa", "numero_casa", "numero"], "");
    const compl   = pick(obj, ["paciente_complemento", "complemento"], "");
    const bairro  = pick(obj, ["paciente_bairro", "bairro", "bairro_paciente"], "");
    const cidade2 = pick(obj, ["paciente_municipio", "paciente_cidade", "municipio", "cidade"], "");
    const cep     = pick(obj, ["paciente_cep", "cep"], "");

    const partes = [];
    if (lograd) partes.push(lograd);
    if (num) partes.push(`Nº ${num}`);
    if (compl) partes.push(compl);
    if (bairro) partes.push(bairro);
    if (cidade2) partes.push(cidade2);
    if (cep) partes.push(`CEP ${cep}`);

    return partes.length ? partes.join(", ") : "—";
  }

  function debounce(fn, wait = 220) {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), wait);
    };
  }

  function isSelect(el) {
    return !!el && String(el.tagName || "").toUpperCase() === "SELECT";
  }
  function isInput(el) {
    const tag = String(el?.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA";
  }

  // =========================
  // Profissional · Autocomplete (3+)
  // =========================
  const PROF_MIN_CHARS = 3;
  let profACEnabled = false;

  function acShow() {
    if (!sugBox) return;
    sugBox.classList.remove("hide");
  }
  function acHide() {
    if (!sugBox) return;
    sugBox.classList.add("hide");
    sugBox.innerHTML = "";
  }
  function acClearSelected() {
    if (inpProfId) inpProfId.value = "";
  }

  async function acFetch(q) {
    // ✅ backend deve buscar em usuarios.nome e usuarios.cbo (e retornar id/nome/cbo)
    const url = `/atendimentos/api/profissionais_sugestao?q=${encodeURIComponent(q)}`;
    const resp = await fetch(url);
    const data = await resp.json();
    return Array.isArray(data) ? data : [];
  }

  function escapeAttr(s) {
    return String(s ?? "").replaceAll('"', "&quot;");
  }

  function acRender(items) {
    if (!sugBox) return;

    if (!items.length) {
      sugBox.innerHTML = `<div class="prof-sug empty">Nenhum resultado</div>`;
      acShow();
      return;
    }

    sugBox.innerHTML = items.map((p) => {
      const id   = p.id != null ? String(p.id) : "";
      const nome = (p.nome || p.name || "").trim() || (id ? `ID ${id}` : "Sem nome");
      const cbo  = (p.cbo || "").trim();

      const meta = [];
      if (cbo) meta.push(`CBO ${cbo}`);
      const metaTxt = meta.length ? ` <span class="muted">(${meta.join(" · ")})</span>` : "";

      // data-label: o que vai entrar no input ao clicar
      const label = cbo ? `${nome} (${cbo})` : nome;

      return `
        <button
          type="button"
          class="prof-sug"
          role="option"
          data-id="${escapeAttr(id)}"
          data-label="${escapeAttr(label)}"
        >
          <strong>${nome}</strong>${metaTxt}
        </button>
      `;
    }).join("");

    acShow();
  }

  const acOnInput = debounce(async () => {
    if (!profACEnabled) return;
    if (!selProf || !isInput(selProf)) return;

    const q = String(selProf.value || "").trim();
    if (q.length < PROF_MIN_CHARS) {
      acHide();
      acClearSelected();
      return;
    }

    try {
      const items = await acFetch(q);
      acRender(items);
    } catch (e) {
      console.warn("[registros] sugestão prof falhou:", e);
      acHide();
    }
  }, 220);

  function initProfAutocomplete() {
    // liga APENAS se:
    // - #f_prof for input (novo)
    // - existir #f_prof_id (hidden) e #f_prof_sugestoes
    if (selProf && isInput(selProf) && inpProfId && sugBox) {
      profACEnabled = true;

      selProf.addEventListener("input", () => {
        // digitou na mão = invalida seleção
        acClearSelected();
        acOnInput();
      });

      selProf.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          acHide();
        }
        if (e.key === "Enter") {
          // Enter = aplicar filtro
          e.preventDefault();
          acHide();
          listar();
        }
      });

      sugBox.addEventListener("click", (e) => {
        const btn = e.target.closest(".prof-sug[data-id]");
        if (!btn) return;

        const id    = btn.getAttribute("data-id") || "";
        const label = btn.getAttribute("data-label") || btn.textContent.trim();

        selProf.value   = label;  // agora pode vir "Nome (CBO)"
        inpProfId.value = id;

        acHide();
        listar(); // escolheu = filtra
      });

      document.addEventListener("click", (e) => {
        if (!profACEnabled) return;
        if (!sugBox || !selProf) return;

        // clique dentro do wrap não fecha
        const wrap = document.getElementById("f_prof_wrap");
        if (wrap && wrap.contains(e.target)) return;

        acHide();
      });

      return true;
    }

    profACEnabled = false;
    return false;
  }

  // ✅ monta params de filtros (reutilizado por listagem, XLSX e PDF)
  function buildFilterParams() {
    const p = new URLSearchParams();

    const qVal = valFiltro(inpBusca?.value);
    if (qVal) p.set("q", qVal);

    // PROF:
    // - se autocomplete ativo: usa #f_prof_id
    // - senão: usa select antigo (#f_prof)
    if (profACEnabled) {
      const profIdVal = valFiltro(inpProfId?.value);
      if (profIdVal) p.set("prof", profIdVal);
    } else {
      const profVal = valFiltro(selProf?.value);
      if (profVal) p.set("prof", profVal);
    }

    const dIni = valFiltro(inpDataIni?.value);
    const dFim = valFiltro(inpDataFim?.value);
    if (dIni) p.set("data_ini", dIni);
    if (dFim) p.set("data_fim", dFim);

    const statusVal = valFiltro(selStatus?.value);
    if (statusVal) p.set("status", statusVal);

    const sexoVal = valFiltro(selSexo?.value);
    if (sexoVal) p.set("sexo", sexoVal);

    const cidVal = valFiltro(inpCID?.value);
    if (cidVal) p.set("cid", cidVal);

    const cidadeVal = valFiltro(inpCidade?.value);
    if (cidadeVal) p.set("cidade", cidadeVal);

    return p;
  }

  function buildListURL() {
    const p = buildFilterParams();
    const qs = p.toString();
    const url = `/registros/api/list${qs ? "?" + qs : ""}`;
    console.debug("[registros] URL montada:", url);
    return url;
  }

  function parseRowFromTR(tr) {
    const raw = tr.getAttribute("data-row") || "{}";
    try {
      return JSON.parse(raw.replaceAll("&quot;", '"'));
    } catch (e) {
      console.warn("[registros] Falha ao parsear data-row:", e);
      return {};
    }
  }

  // =========================
  // Render tabela
  // =========================
  function renderTabela(rows) {
    if (!rows || !rows.length) {
      tbody.innerHTML = `<tr><td colspan="5">Nenhum registro encontrado.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map((r) => {
      const paciente = pick(r, ["paciente_nome", "nome_paciente", "nome"], "—");
      const cns      = pick(r, ["paciente_cns", "cns", "cartao_sus"], "—");

      const dtRaw = pick(r, ["data_atendimento", "data", "data_iso", "created_at"], "—");
      const dt    = dtRaw === "—" ? "—" : fmtDataBR(dtRaw);

      const prof  = profNameFrom(r);

      const dataRow = JSON.stringify(r).replaceAll('"', "&quot;");

      return `
        <tr data-row="${dataRow}">
          <td>${safe(paciente)}</td>
          <td>${safe(prof)}</td>
          <td>${safe(dt)}</td>
          <td>${safe(cns)}</td>
          <td class="nowrap">
            <button class="btn primary" data-act="ver">Ver mais</button>
          </td>
        </tr>
      `;
    }).join("");
  }

  // =========================
  // Paginação
  // =========================
  function updatePaginationUI(total, totalPages, pageCount, startIndex) {
    const from = total ? startIndex + 1 : 0;
    const to   = total ? Math.min(startIndex + pageCount, total) : 0;

    if (pagInfo) pagInfo.textContent = `Mostrando ${from}–${to} de ${total} registro(s)`;

    if (lblResumo) {
      lblResumo.textContent = total
        ? `Encontrados ${total} registro(s).`
        : "Nenhum registro encontrado.";
    }

    if (pagAtualEl) pagAtualEl.textContent = String(total ? currentPage : 1);
    if (pagTotalEl) pagTotalEl.textContent = String(total ? totalPages : 1);

    const disableFirstPrev = currentPage <= 1 || !total;
    const disableNextLast  = currentPage >= totalPages || !total;

    [btnPagFirst, btnPagPrev].forEach((btn) => btn && (btn.disabled = disableFirstPrev));
    [btnPagNext,  btnPagLast].forEach((btn) => btn && (btn.disabled = disableNextLast));
  }

  function renderPagina() {
    const total = allRows.length;
    const totalPages = total ? Math.ceil(total / PAGE_SIZE) : 1;

    if (currentPage < 1) currentPage = 1;
    if (currentPage > totalPages) currentPage = totalPages;

    const start = (currentPage - 1) * PAGE_SIZE;
    const pageRows = allRows.slice(start, start + PAGE_SIZE);

    if (!total) {
      renderTabela([]);
      updatePaginationUI(0, 1, 0, 0);
      return;
    }

    renderTabela(pageRows);
    updatePaginationUI(total, totalPages, pageRows.length, start);
  }

  function goToPage(where) {
    const total = allRows.length;
    if (!total) {
      currentPage = 1;
      renderPagina();
      return;
    }
    const totalPages = Math.ceil(total / PAGE_SIZE);

    switch (where) {
      case "first": currentPage = 1; break;
      case "prev":  currentPage = Math.max(1, currentPage - 1); break;
      case "next":  currentPage = Math.min(totalPages, currentPage + 1); break;
      case "last":  currentPage = totalPages; break;
    }
    renderPagina();
  }

  // =========================
  // Modal
  // =========================
  function fillModalHeaderBadges(obj) {
    const nome  = pick(obj, ["paciente_nome", "nome_paciente", "nome"], "");
    const pront = pick(obj, ["paciente_prontuario", "prontuario", "prontuario_num"], "");
    const cpf   = pick(obj, ["paciente_cpf", "cpf"], "");

    const parts = [];
    if (nome)  parts.push(`Paciente: ${nome}`);
    if (cpf)   parts.push(`CPF: ${cpf}`);
    if (pront) parts.push(`Prontuário: ${pront}`);

    if (mrSubtitle) setText(mrSubtitle, parts.length ? parts.join(" · ") : "—");

    const dtRaw = pick(obj, ["data_atendimento", "data", "data_iso", "created_at"], "");
    const dt    = dtRaw ? fmtDataBR(dtRaw) : "—";
    if (mrBadgeData) setText(mrBadgeData, `📅 ${dt}`);

    const statusRaw = pick(obj, ["status", "situacao", "comparecimento", "paciente_status"], "");
    const label = normalizeStatusLabel(statusRaw);
    if (mrBadgeStatus) setText(mrBadgeStatus, `${statusEmoji(label)} ${label}`);

    const cbo = pick(obj, ["profissional_cbo", "cbo_profissional", "cbo"], "");
    if (mrBadgeCbo) setText(mrBadgeCbo, `🧩 ${cbo ? `CBO ${cbo}` : "CBO —"}`);
  }

  function buildKV(obj, ignoreKeysSet) {
    if (!mrKV) return;
    mrKV.innerHTML = "";

    const keys = Object.keys(obj || {});
    if (!keys.length) return;

    keys.forEach((k) => {
      if (ignoreKeysSet && ignoreKeysSet.has(k)) return;

      const v = obj[k];

      const kEl = document.createElement("div");
      kEl.className = "mr-k";
      kEl.textContent = k;

      const vEl = document.createElement("div");
      vEl.className = "mr-v";
      vEl.textContent = v == null || v === "" ? "—" : String(v);

      mrKV.appendChild(kEl);
      mrKV.appendChild(vEl);
    });
  }

  function openModalFromTR(tr) {
    if (!dlg) {
      console.warn("[registros] dialog #modal-registro não encontrado.");
      return;
    }

    const obj = parseRowFromTR(tr);
    lastModalRowObj = obj;

    fillModalHeaderBadges(obj);

    mapFill(obj, [
      { el: mrProf,         keys: ["profissional_nome","profissional","nome_profissional","usuario_nome","nome_usuario"], fmt: (_, o) => profNameFrom(o) },
      { el: mrProfCns,      keys: ["profissional_cns","cns_profissional"] },
      { el: mrProfCbo,      keys: ["profissional_cbo","cbo_profissional","cbo"] },

      { el: mrProcedimento, keys: ["procedimento","procedimento_nome","procedimento_desc","ap_procedimento"] },
      { el: mrSigtap,       keys: ["codigo_sigtap","cod_sigtap","sigtap","ap_codigo_sigtap"] },

      { el: mrCid,          keys: ["paciente_cid","cid","cid_principal","cid10"] },

      { el: mrData,         keys: ["data_atendimento","data","data_iso","created_at"], fmt: (v) => (v === "—" ? "—" : fmtDataBR(v)) },

      { el: mrStatus,       keys: ["status","situacao","comparecimento","paciente_status"], fmt: (v) => normalizeStatusLabel(v) },
      { el: mrStatusJust,   keys: ["status_justificativa","justificativa","motivo"] },

      { el: mrEvolucao,     keys: ["evolucao","evolucao_texto","observacao","observacoes"] },
    ]);

    mapFill(obj, [
      { el: mrPaciente,   keys: ["paciente_nome","nome_paciente","nome"] },
      { el: mrProntuario, keys: ["paciente_prontuario","prontuario","prontuario_num"] },
      { el: mrPacIdade,   keys: ["paciente_idade","idade"] },
      { el: mrPacMod,     keys: ["paciente_mod","mod","modalidade"] },

      { el: mrPacCPF,     keys: ["paciente_cpf","cpf"] },
      { el: mrPacCNS,     keys: ["paciente_cns","cns","cartao_sus"] },

      { el: mrPacNasc,    keys: ["paciente_nascimento","nascimento","data_nascimento","dt_nasc"], fmt: (v) => (v === "—" ? "—" : fmtDataBR(v)) },
      { el: mrPacSexo,    keys: ["paciente_sexo","sexo","sex"] },

      { el: mrPacCidade,  keys: ["paciente_cidade","paciente_municipio","cidade","municipio","cidade_paciente","municipio_paciente"] },
      { el: mrPacTel,     keys: ["__tel__"], fmt: (_, o) => formatTelefones(o) },
      { el: mrPacEndereco,keys: ["__end__"], fmt: (_, o) => formatEndereco(o) },
    ]);

    const ignoreKeys = new Set([
      "paciente_nome","nome_paciente","nome",
      "paciente_cpf","cpf","paciente_cns","cns","cartao_sus",
      "paciente_prontuario","prontuario","prontuario_num",
      "paciente_idade","idade","paciente_mod","mod","modalidade",
      "paciente_nascimento","nascimento","data_nascimento","dt_nasc",
      "paciente_sexo","sexo","sex",
      "paciente_telefone1","telefone1","telefone","telefone_paciente",
      "paciente_telefone2","telefone2",
      "paciente_telefone3","telefone3","celular","celular_paciente",
      "paciente_logradouro","logradouro","rua",
      "paciente_numero_casa","numero_casa","numero",
      "paciente_complemento","complemento",
      "paciente_bairro","bairro","bairro_paciente",
      "paciente_municipio","paciente_cidade","municipio","cidade","cidade_paciente","municipio_paciente",
      "paciente_cep","cep",
      "profissional_nome","profissional","nome_profissional","usuario_nome","nome_usuario",
      "profissional_id","prof_id","id_profissional","usuario_id",
      "profissional_cns","cns_profissional",
      "profissional_cbo","cbo_profissional","cbo",
      "procedimento","procedimento_nome","procedimento_desc","ap_procedimento",
      "codigo_sigtap","cod_sigtap","sigtap","ap_codigo_sigtap",
      "paciente_cid","cid","cid_principal","cid10",
      "data_atendimento","data","data_iso","created_at",
      "status","situacao","comparecimento","paciente_status",
      "status_justificativa","justificativa","motivo",
      "evolucao","evolucao_texto","observacao","observacoes",
    ]);
    buildKV(obj, ignoreKeys);

    // reseta abas (volta para atendimento)
    if (dlg) {
      const tabs   = dlg.querySelectorAll(".mr-tab");
      const panels = dlg.querySelectorAll(".mr-panel");
      tabs.forEach((t) => t.classList.remove("is-active"));
      panels.forEach((p) => p.classList.remove("is-active"));

      const tabAt = dlg.querySelector('.mr-tab[data-tab="atendimento"]');
      const panAt = dlg.querySelector('.mr-panel[data-panel="atendimento"]');
      tabAt && tabAt.classList.add("is-active");
      panAt && panAt.classList.add("is-active");
    }

    try {
      if (typeof dlg.showModal === "function") dlg.showModal();
      else dlg.setAttribute("open", "open");
    } catch (err) {
      console.error("[registros] Erro ao abrir modal:", err);
      dlg.setAttribute("open", "open");
    }
  }

  function initModalTabs() {
    if (!dlg) return;
    const tabs   = dlg.querySelectorAll(".mr-tab");
    const panels = dlg.querySelectorAll(".mr-panel");

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const tabName = tab.getAttribute("data-tab");
        if (!tabName) return;

        tabs.forEach((t) => t.classList.remove("is-active"));
        panels.forEach((p) => {
          p.classList.toggle("is-active", p.getAttribute("data-panel") === tabName);
        });

        tab.classList.add("is-active");
      });
    });
  }

  function initCopyEvolucao() {
    if (!mrBtnCopyEvo) return;

    mrBtnCopyEvo.addEventListener("click", async () => {
      const txt = (mrEvolucao?.textContent || "").trim();
      if (!txt || txt === "—") {
        mrBtnCopyEvo.textContent = "⚠️ Sem texto";
        setTimeout(() => (mrBtnCopyEvo.textContent = "📎 Copiar"), 1200);
        return;
      }

      try {
        await navigator.clipboard.writeText(txt);
        mrBtnCopyEvo.textContent = "✅ Copiado";
      } catch (e) {
        console.warn("[registros] clipboard falhou:", e);
        mrBtnCopyEvo.textContent = "⚠️ Falhou";
      }
      setTimeout(() => (mrBtnCopyEvo.textContent = "📎 Copiar"), 1200);
    });
  }

  // =========================
  // Ações
  // =========================
  async function listar() {
    const url = buildListURL();
    try {
      const resp = await fetch(url);
      const rows = await resp.json();
      const arr  = Array.isArray(rows) ? rows : [];
      console.debug("[registros] itens recebidos:", arr.length);

      allRows     = arr;
      currentPage = 1;
      renderPagina();
    } catch (err) {
      console.error("[registros] Erro ao listar:", err);
      allRows = [];
      tbody.innerHTML = `<tr><td colspan="5">Erro ao carregar registros.</td></tr>`;
      lblResumo && (lblResumo.textContent = "Erro ao carregar registros.");
      updatePaginationUI(0, 1, 0, 0);
    }
  }

  function limpar() {
    frm && frm.reset();

    // limpa selects
    if (!profACEnabled && selProf && isSelect(selProf)) selProf.value = "";
    selStatus && (selStatus.value = "");
    selSexo   && (selSexo.value = "");

    // limpa autocomplete
    if (profACEnabled && selProf && isInput(selProf)) selProf.value = "";
    if (inpProfId) inpProfId.value = "";
    acHide();

    lastModalRowObj = null;
    listar();
  }

  function exportarXLSX() {
    const p = buildFilterParams();
    const qs = p.toString();
    const urlXlsx = `/registros/exportar_xlsx${qs ? "?" + qs : ""}`;
    console.debug("[registros] Exportando XLSX:", urlXlsx);
    window.location.href = urlXlsx;
  }

  function exportarEvolucoesPDF() {
    const p = buildFilterParams();

    const pid = lastModalRowObj
      ? (lastModalRowObj.paciente_id ?? lastModalRowObj.pacienteId ?? "")
      : "";

    if (pid !== undefined && pid !== null && String(pid).trim() !== "") {
      p.set("paciente_id", String(pid).trim());
    }

    const qs = p.toString();
    const urlPdf = `/registros/evolucoes/pdf${qs ? "?" + qs : ""}`;

    console.debug("[registros] Exportando Evoluções PDF:", urlPdf);
    window.open(urlPdf, "_blank");
  }

  // =========================
  // Profissionais dinâmicos (legado select)
  // =========================
  async function carregarProfissionaisSelectLegado() {
    if (!selProf || !isSelect(selProf)) return;

    try {
      const resp = await fetch("/atendimentos/api/profissionais");
      const data = await resp.json();

      if (!Array.isArray(data) || !data.length) {
        console.warn("[registros] Nenhum profissional retornado de /atendimentos/api/profissionais");
        return;
      }

      selProf.innerHTML = "";
      const optAll = document.createElement("option");
      optAll.value = "";
      optAll.textContent = "Todos";
      selProf.appendChild(optAll);

      data.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id != null ? String(p.id) : "";
        let label = p.nome || (p.id != null ? `ID ${p.id}` : "Sem nome");
        if (p.cbo) label += ` (${p.cbo})`;
        opt.textContent = label;
        selProf.appendChild(opt);
      });
    } catch (e) {
      console.warn("[registros] Não foi possível carregar profissionais dinâmicos:", e);
    }
  }

  // =========================
  // Eventos
  // =========================
  frm?.addEventListener("submit", (e) => {
    e.preventDefault();
    listar();
  });

  btnFiltrar?.addEventListener("click", (e) => {
    e.preventDefault();
    listar();
  });

  btnLimpar?.addEventListener("click", (e) => {
    e.preventDefault();
    limpar();
  });

  btnExportar?.addEventListener("click", (e) => {
    e.preventDefault();
    exportarXLSX();
  });

  btnExportarEvoPdf?.addEventListener("click", (e) => {
    e.preventDefault();
    exportarEvolucoesPDF();
  });

  // selects e datas: ao mudar, filtra
  [selStatus, selSexo, inpDataIni, inpDataFim].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => listar());
  });

  // select de prof (legado) filtra ao mudar
  if (selProf && isSelect(selProf)) {
    selProf.addEventListener("change", () => listar());
  }

  // busca: Enter filtra
  inpBusca?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      listar();
    }
  });

  if (tbl) {
    tbl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act='ver']");
      if (!btn) return;
      const tr = btn.closest("tr");
      if (!tr) return;
      openModalFromTR(tr);
    });
  }

  document.addEventListener("click", (e) => {
    if (!dlg) return;
    if (e.target.closest("[value='close']")) {
      if (typeof dlg.close === "function") dlg.close();
      else dlg.removeAttribute("open");
    }
  });

  [
    [btnPagFirst, "first"],
    [btnPagPrev,  "prev"],
    [btnPagNext,  "next"],
    [btnPagLast,  "last"],
  ].forEach(([btn, where]) => {
    if (!btn) return;
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      goToPage(where);
    });
  });

  // =========================
  // Init
  // =========================
  (async () => {
    initModalTabs();
    initCopyEvolucao();

    // tenta ligar autocomplete; se não der, cai no select legado
    const okAC = initProfAutocomplete();
    if (!okAC) {
      await carregarProfissionaisSelectLegado();
    }

    listar();
  })();
})();
