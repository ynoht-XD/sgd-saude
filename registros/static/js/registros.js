// registros/static/js/registros.js
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const frm = $("#frmFiltros");
  const inpBusca = $("#f_busca");
  const selProf = $("#f_prof");
  const inpProfId = $("#f_prof_id");
  const sugBox = $("#f_prof_sugestoes");

  const inpDataIni = $("#f_data_ini");
  const inpDataFim = $("#f_data_fim");
  const selStatus = $("#f_status");
  const selSexo = $("#f_sexo");
  const inpCID = $("#f_cid");
  const inpCidade = $("#f_cidade");

  const btnFiltrar = $("#btnFiltrar");
  const btnLimpar = $("#btnLimpar");
  const btnExportar = $("#btnExportar");

  const tbl = $("#tblRegistros");
  const tbody = $("#tblRegistros tbody");
  const lblResumo = $("#lblResumo");

  const pagInfo = $("#pagInfo");
  const pagAtualEl = $("#pagAtual");
  const pagTotalEl = $("#pagTotal");
  const btnPagFirst = $("#pagFirst");
  const btnPagPrev = $("#pagPrev");
  const btnPagNext = $("#pagNext");
  const btnPagLast = $("#pagLast");

  const PAGE_SIZE = 15;
  let allRows = [];
  let currentPage = 1;
  let lastModalRowObj = null;

  const dlg = $("#modal-registro");

  const mrSubtitle = $("#mr_subtitle");
  const mrBadgeData = $("#mr_badge_data");
  const mrBadgeStatus = $("#mr_badge_status");
  const mrBadgeCbo = $("#mr_badge_cbo");
  const mrBadgeOculta = $("#mr_badge_oculta");

  const mrBtnCopyEvo = $("#mr_btn_copiar_evo");
  const mrBtnCopyOculta = $("#mr_btn_copiar_oculta");

  const mrProf = $("#mr_profissional");
  const mrProfCns = $("#mr_prof_cns");
  const mrProfCbo = $("#mr_prof_cbo");
  const mrProcedimento = $("#mr_procedimento");
  const mrSigtap = $("#mr_sigtap");
  const mrCid = $("#mr_cid");
  const mrData = $("#mr_data");
  const mrStatus = $("#mr_status");
  const mrStatusJust = $("#mr_status_just");
  const mrEvolucao = $("#mr_evolucao");

  const mrPaciente = $("#mr_paciente");
  const mrProntuario = $("#mr_prontuario");
  const mrPacIdade = $("#mr_paciente_idade");
  const mrPacMod = $("#mr_paciente_mod");
  const mrPacCPF = $("#mr_pac_cpf");
  const mrPacCNS = $("#mr_pac_cns");
  const mrPacNasc = $("#mr_pac_nasc");
  const mrPacSexo = $("#mr_pac_sexo");
  const mrPacTel = $("#mr_pac_tel");
  const mrPacCidade = $("#mr_pac_cidade");
  const mrPacEndereco = $("#mr_pac_endereco");

  const mrOcultaTitulo = $("#mr_oculta_titulo");
  const mrOcultaSub = $("#mr_oculta_sub");
  const mrOcultaSituacao = $("#mr_oculta_situacao");
  const mrOcultaTotal = $("#mr_oculta_total");
  const mrOcultaVisivel = $("#mr_oculta_visivel");
  const mrEvolucaoOculta = $("#mr_evolucao_oculta");

  let cardsWrap = $("#cardsRegistros");
  let selOrdem = $("#f_ordem");

  const PROFISSIONAIS = {
    "101": "Dr. João (Clínico)",
    "102": "Dra. Maria (Psicologia)",
    "103": "Fisio Pedro (Fisioterapia)",
  };

  const safe = (v, alt = "—") =>
    v === undefined || v === null || String(v).trim() === "" ? alt : String(v);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }

  function valFiltro(v) {
    if (v == null) return "";
    const s = String(v).trim();
    if (!s) return "";
    const low = s.toLowerCase();
    if (["todos", "todo", "-", "*"].includes(low)) return "";
    return s;
  }

  function hojeISO() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dia = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dia}`;
  }

  function inicioCompetenciaISO() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    return `${y}-${m}-01`;
  }

  function aplicarCompetenciaPadrao() {
    if (inpDataIni && !inpDataIni.value) inpDataIni.value = inicioCompetenciaISO();
    if (inpDataFim && !inpDataFim.value) inpDataFim.value = hojeISO();
  }

  function fmtDataBR(d) {
    if (!d) return "—";
    const s = String(d).trim();
    if (!s) return "—";

    const iso = s.slice(0, 10);

    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
      const [y, m, dia] = iso.split("-");
      return `${dia}/${m}/${y}`;
    }

    return s;
  }

  function toDateNumber(v) {
    const s = String(v || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return 0;
    return Number(s.replaceAll("-", ""));
  }

  function pick(obj, keys, fallback = "—") {
    for (const k of keys) {
      if (k in obj && obj[k] != null && obj[k] !== "") return obj[k];
    }
    return fallback;
  }

  function setText(el, value, fallback = "—") {
    if (!el) return;
    el.textContent = safe(value, fallback);
  }

  function normalizeStatusLabel(s) {
    const v = String(s || "").trim();
    if (!v) return "—";
    const low = v.toLowerCase();

    if (low.includes("pres") || low === "ok" || low === "compareceu" || low === "realizado") return "Presente";
    if (low.includes("falta") || low.includes("falt")) return "Faltoso";
    if (low.includes("just")) return "Justificado";
    if (low.includes("admiss")) return "Admissão";
    if (low.includes("alta")) return "Alta";

    return v;
  }

  function statusEmoji(label) {
    const low = String(label || "").toLowerCase();
    if (low.includes("presente")) return "✅";
    if (low.includes("just")) return "🟣";
    if (low.includes("falt")) return "❌";
    if (low.includes("admiss")) return "🟢";
    if (low.includes("alta")) return "🏁";
    return "ℹ️";
  }

  function profNameFrom(obj) {
    const direct = pick(obj, ["profissional_nome", "profissional", "nome_profissional", "usuario_nome", "nome_usuario"], "");
    if (direct && direct !== "—") return direct;

    const pid = obj.profissional_id ?? obj.prof_id ?? obj.id_profissional ?? obj.usuario_id ?? "";
    if (pid && String(pid) in PROFISSIONAIS) return PROFISSIONAIS[String(pid)];
    return pid ? `ID ${pid}` : "—";
  }

  function pacienteNameFrom(obj) {
    return pick(obj, ["pac__nome", "paciente_nome", "nome_paciente", "nome"], "—");
  }

  function dataFrom(obj) {
    return pick(obj, ["data_atendimento", "data", "data_iso", "created_at"], "");
  }

  function cnsFrom(obj) {
    return pick(obj, ["pac__cns", "paciente_cns", "cns", "cartao_sus"], "—");
  }

  function formatTelefones(obj) {
    const tels = [
      pick(obj, ["pac__telefone", "paciente_telefone1", "telefone1", "telefone", "telefone_paciente"], ""),
      pick(obj, ["pac__telefone2", "paciente_telefone2", "telefone2"], ""),
      pick(obj, ["pac__telefone3", "paciente_telefone3", "telefone3", "celular", "celular_paciente"], ""),
    ].map(v => String(v || "").trim()).filter(Boolean);

    return [...new Set(tels)].join(" • ") || "—";
  }

  function formatEndereco(obj) {
    const partes = [];

    const lograd = pick(obj, ["pac__logradouro", "paciente_logradouro", "logradouro", "rua"], "");
    const num = pick(obj, ["pac__numero", "paciente_numero_casa", "numero_casa", "numero"], "");
    const compl = pick(obj, ["pac__complemento", "paciente_complemento", "complemento"], "");
    const bairro = pick(obj, ["pac__bairro", "paciente_bairro", "bairro", "bairro_paciente"], "");
    const cidade2 = pick(obj, ["pac__municipio", "pac__cidade", "paciente_municipio", "paciente_cidade", "municipio", "cidade"], "");
    const uf = pick(obj, ["pac__uf", "uf"], "");
    const cep = pick(obj, ["pac__cep", "paciente_cep", "cep"], "");

    if (lograd) partes.push(lograd);
    if (num) partes.push(`Nº ${num}`);
    if (compl) partes.push(compl);
    if (bairro) partes.push(bairro);
    if (cidade2) partes.push(uf ? `${cidade2}/${uf}` : cidade2);
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

  function mapFill(obj, mapping) {
    mapping.forEach((m) => {
      const raw = pick(obj, m.keys, m.fallback ?? "—");
      const val = typeof m.fmt === "function" ? m.fmt(raw, obj) : raw;
      setText(m.el, val, m.fallback ?? "—");
    });
  }

  function decodeDataRow(raw) {
    try {
      return JSON.parse(String(raw || "{}").replaceAll("&quot;", '"'));
    } catch {
      return {};
    }
  }

  function evoOcultaInfo(obj) {
    const total = Number(obj.evo_oculta_total || 0);
    const visivel = Number(obj.evo_oculta_visivel || 0);
    const situacao = String(obj.evo_oculta_situacao || "sem_evolucao_oculta");
    const texto = String(obj.evolucoes_ocultas_visiveis || "").trim();

    if (situacao === "visivel" || visivel > 0) {
      return {
        tipo: "visivel",
        badge: "🔓 Privada visível",
        titulo: "Evoluções privadas liberadas",
        sub: "Você é o autor ou possui CBO autorizado para visualizar.",
        pill: "Visível",
        total,
        visivel,
        texto: texto || "—",
      };
    }

    if (situacao === "restrita" || total > 0) {
      return {
        tipo: "restrita",
        badge: "🔒 Privada restrita",
        titulo: "Evoluções privadas restritas",
        sub: "Existe evolução privada neste atendimento, mas ela não está liberada para seu usuário/CBO.",
        pill: "Restrita",
        total,
        visivel,
        texto: "Conteúdo restrito.",
      };
    }

    return {
      tipo: "sem",
      badge: "🔘 Sem evolução privada",
      titulo: "Sem evolução privada",
      sub: "Este atendimento não possui evolução privada registrada.",
      pill: "Sem registro",
      total: 0,
      visivel: 0,
      texto: "—",
    };
  }

  function setModalTab(tabName) {
    if (!dlg) return;

    dlg.querySelectorAll(".mr-tab").forEach((t) => {
      t.classList.toggle("is-active", t.getAttribute("data-tab") === tabName);
    });

    dlg.querySelectorAll(".mr-panel").forEach((p) => {
      p.classList.toggle("is-active", p.getAttribute("data-panel") === tabName);
    });
  }

  function fillModalHeaderBadges(obj) {
    const nome = pick(obj, ["pac__nome", "paciente_nome", "nome_paciente", "nome"], "");
    const pront = pick(obj, ["pac__prontuario", "paciente_prontuario", "prontuario", "prontuario_num"], "");
    const cpf = pick(obj, ["pac__cpf", "paciente_cpf", "cpf"], "");

    const parts = [];
    if (nome) parts.push(`Paciente: ${nome}`);
    if (cpf) parts.push(`CPF: ${cpf}`);
    if (pront) parts.push(`Prontuário: ${pront}`);

    setText(mrSubtitle, parts.length ? parts.join(" · ") : "—");

    const dtRaw = dataFrom(obj);
    setText(mrBadgeData, `📅 ${dtRaw ? fmtDataBR(dtRaw) : "—"}`);

    const label = normalizeStatusLabel(pick(obj, ["pac__status", "status", "situacao", "comparecimento", "paciente_status"], ""));
    setText(mrBadgeStatus, `${statusEmoji(label)} ${label}`);

    const cbo = pick(obj, ["profissional_cbo", "cbo_profissional", "cbo", "ag__prof_cbo"], "");
    setText(mrBadgeCbo, `🧩 ${cbo ? `CBO ${cbo}` : "CBO —"}`);

    const info = evoOcultaInfo(obj);
    setText(mrBadgeOculta, info.badge);
    mrBadgeOculta?.classList.remove("is-visible", "is-restricted", "is-empty");
    mrBadgeOculta?.classList.add(
      info.tipo === "visivel" ? "is-visible" :
      info.tipo === "restrita" ? "is-restricted" :
      "is-empty"
    );
  }

  function fillModalEvolucaoPrivada(obj) {
    const info = evoOcultaInfo(obj);

    setText(mrOcultaTitulo, info.titulo);
    setText(mrOcultaSub, info.sub);
    setText(mrOcultaSituacao, info.pill);
    setText(mrOcultaTotal, info.total);
    setText(mrOcultaVisivel, info.visivel);
    setText(mrEvolucaoOculta, info.texto);

    mrOcultaSituacao?.classList.remove("is-visible", "is-restricted", "is-empty");
    mrOcultaSituacao?.classList.add(
      info.tipo === "visivel" ? "is-visible" :
      info.tipo === "restrita" ? "is-restricted" :
      "is-empty"
    );
  }

  function openModalFromObj(obj) {
    if (!dlg) return;

    lastModalRowObj = obj;
    fillModalHeaderBadges(obj);

    mapFill(obj, [
      { el: mrProf, keys: ["profissional_nome", "profissional", "nome_profissional", "usuario_nome", "nome_usuario", "ag__profissional"], fmt: (_, o) => profNameFrom(o) },
      { el: mrProfCns, keys: ["profissional_cns", "cns_profissional"] },
      { el: mrProfCbo, keys: ["profissional_cbo", "cbo_profissional", "cbo", "ag__prof_cbo"] },
      { el: mrProcedimento, keys: ["procedimento", "procedimento_nome", "procedimento_desc", "ap_procedimento"] },
      { el: mrSigtap, keys: ["codigo_sigtap", "cod_sigtap", "sigtap", "ap_codigo_sigtap"] },
      { el: mrCid, keys: ["pac__cid", "paciente_cid", "cid", "cid_principal", "cid10"] },
      { el: mrData, keys: ["data_atendimento", "data", "data_iso", "created_at"], fmt: (v) => (v === "—" ? "—" : fmtDataBR(v)) },
      { el: mrStatus, keys: ["status", "situacao", "comparecimento", "paciente_status", "pac__status"], fmt: (v) => normalizeStatusLabel(v) },
      { el: mrStatusJust, keys: ["status_justificativa", "justificativa", "motivo"] },
      { el: mrEvolucao, keys: ["evolucao", "evolucao_texto", "observacao", "observacoes"] },
    ]);

    mapFill(obj, [
      { el: mrPaciente, keys: ["pac__nome", "paciente_nome", "nome_paciente", "nome"] },
      { el: mrProntuario, keys: ["pac__prontuario", "paciente_prontuario", "prontuario", "prontuario_num"] },
      { el: mrPacIdade, keys: ["pac__idade", "paciente_idade", "idade"] },
      { el: mrPacMod, keys: ["pac__mod", "paciente_mod", "mod", "modalidade"] },
      { el: mrPacCPF, keys: ["pac__cpf", "paciente_cpf", "cpf"] },
      { el: mrPacCNS, keys: ["pac__cns", "paciente_cns", "cns", "cartao_sus"] },
      { el: mrPacNasc, keys: ["pac__nascimento", "paciente_nascimento", "nascimento", "data_nascimento", "dt_nasc"], fmt: (v) => (v === "—" ? "—" : fmtDataBR(v)) },
      { el: mrPacSexo, keys: ["pac__sexo", "paciente_sexo", "sexo", "sex"] },
      { el: mrPacCidade, keys: ["pac__municipio", "pac__cidade", "paciente_cidade", "paciente_municipio", "cidade", "municipio", "cidade_paciente", "municipio_paciente"] },
      { el: mrPacTel, keys: ["__tel__"], fmt: (_, o) => formatTelefones(o) },
      { el: mrPacEndereco, keys: ["__end__"], fmt: (_, o) => formatEndereco(o) },
    ]);

    fillModalEvolucaoPrivada(obj);
    setModalTab("atendimento");

    try {
      if (typeof dlg.showModal === "function") dlg.showModal();
      else dlg.setAttribute("open", "open");
    } catch {
      dlg.setAttribute("open", "open");
    }
  }

  function ordenarRows(rows) {
    const ordem = selOrdem?.value || "data_desc";
    const arr = [...rows];

    const byPaciente = (a, b) => pacienteNameFrom(a).localeCompare(pacienteNameFrom(b), "pt-BR");
    const byProf = (a, b) => profNameFrom(a).localeCompare(profNameFrom(b), "pt-BR");
    const byData = (a, b) => toDateNumber(dataFrom(a)) - toDateNumber(dataFrom(b));

    if (ordem === "paciente_az") arr.sort(byPaciente);
    else if (ordem === "paciente_za") arr.sort((a, b) => byPaciente(b, a));
    else if (ordem === "prof_az") arr.sort(byProf);
    else if (ordem === "data_asc") arr.sort(byData);
    else arr.sort((a, b) => byData(b, a));

    return arr;
  }

  function ensureCardsUI() {
    if (selOrdem && cardsWrap) return;

    const resultadosCard = tbl?.closest(".card") || $("#paginacao")?.closest(".card");
    if (!resultadosCard) return;

    if (!selOrdem) {
      const toolbar = document.createElement("div");
      toolbar.className = "result-toolbar";
      toolbar.innerHTML = `
        <div class="muted" id="lblResumoCards"></div>
        <div class="field small">
          <label for="f_ordem">Ordenar</label>
          <select id="f_ordem" name="ordem">
            <option value="data_desc">Mais recentes</option>
            <option value="data_asc">Mais antigos</option>
            <option value="paciente_az">Paciente A-Z</option>
            <option value="paciente_za">Paciente Z-A</option>
            <option value="prof_az">Profissional A-Z</option>
          </select>
        </div>
      `;

      const oldResumo = $("#lblResumo");
      if (oldResumo) oldResumo.style.display = "none";

      const tabelaWrap = tbl?.closest(".tabela-wrap");
      resultadosCard.insertBefore(toolbar, tabelaWrap || $("#paginacao") || resultadosCard.firstChild);

      selOrdem = $("#f_ordem");
    }

    if (!cardsWrap) {
      cardsWrap = document.createElement("div");
      cardsWrap.id = "cardsRegistros";
      cardsWrap.className = "registros-cards";

      const tabelaWrap = tbl?.closest(".tabela-wrap");
      if (tabelaWrap) {
        tabelaWrap.insertAdjacentElement("beforebegin", cardsWrap);
        tabelaWrap.style.display = "none";
      } else {
        resultadosCard.insertBefore(cardsWrap, $("#paginacao") || null);
      }
    }

    selOrdem?.addEventListener("change", () => {
      currentPage = 1;
      renderPagina();
    });
  }

  function renderCards(rows) {
    if (!cardsWrap) return;

    if (!rows || !rows.length) {
      cardsWrap.innerHTML = `<div class="empty-state">Nenhum registro encontrado.</div>`;
      return;
    }

    cardsWrap.innerHTML = rows.map((r) => {
      const paciente = pacienteNameFrom(r);
      const cns = cnsFrom(r);
      const dtRaw = dataFrom(r);
      const dt = dtRaw ? fmtDataBR(dtRaw) : "—";
      const prof = profNameFrom(r);
      const status = normalizeStatusLabel(pick(r, ["status", "situacao", "comparecimento", "paciente_status", "pac__status"], ""));
      const cid = pick(r, ["pac__cid", "paciente_cid", "cid", "cid_principal", "cid10"], "");
      const proc = pick(r, ["procedimento", "procedimento_nome", "procedimento_desc", "ap_procedimento"], "");

      const info = evoOcultaInfo(r);
      const privClass =
        info.tipo === "visivel" ? "is-visible" :
        info.tipo === "restrita" ? "is-restricted" :
        "is-empty";

      const privIcon =
        info.tipo === "visivel" ? "🔓" :
        info.tipo === "restrita" ? "🔒" :
        "—";

      const dataRow = JSON.stringify(r).replaceAll('"', "&quot;");

      return `
        <article class="registro-card" data-row="${dataRow}">
          <div class="registro-top">
            <strong title="${escapeAttr(paciente)}">${escapeHtml(paciente)}</strong>
            <span class="badge">${escapeHtml(statusEmoji(status))} ${escapeHtml(status)}</span>
          </div>

          <div class="registro-meta">
            <span>📅 ${escapeHtml(dt)}</span>
            <span>👤 ${escapeHtml(prof)}</span>
            ${cid ? `<span>🏷️ CID ${escapeHtml(cid)}</span>` : ""}
            ${proc ? `<span class="registro-proc">🧾 ${escapeHtml(proc)}</span>` : ""}
          </div>

          <div class="registro-extra">
            <span>CNS: ${escapeHtml(cns)}</span>
            <span class="grid-priv ${privClass}">${privIcon}</span>
          </div>

          <div class="registro-actions">
            <button class="btn primary" type="button" data-act="ver-card">Ver mais</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderTabelaCompat(rows) {
    if (!tbody) return;

    if (!rows || !rows.length) {
      tbody.innerHTML = `<tr><td colspan="6">Nenhum registro encontrado.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map((r) => {
      const paciente = pacienteNameFrom(r);
      const cns = cnsFrom(r);
      const dtRaw = dataFrom(r);
      const dt = dtRaw ? fmtDataBR(dtRaw) : "—";
      const prof = profNameFrom(r);
      const status = normalizeStatusLabel(pick(r, ["status", "situacao", "comparecimento", "paciente_status", "pac__status"], ""));

      const info = evoOcultaInfo(r);
      const privBadge =
        info.tipo === "visivel" ? `<span class="grid-priv is-visible">🔓</span>` :
        info.tipo === "restrita" ? `<span class="grid-priv is-restricted">🔒</span>` :
        `<span class="grid-priv is-empty">—</span>`;

      const dataRow = JSON.stringify(r).replaceAll('"', "&quot;");

      return `
        <tr data-row="${dataRow}">
          <td>${escapeHtml(paciente)} ${privBadge}</td>
          <td>${escapeHtml(prof)}</td>
          <td>${escapeHtml(dt)}</td>
          <td>${escapeHtml(status)}</td>
          <td>${escapeHtml(cns)}</td>
          <td class="nowrap">
            <button class="btn primary" data-act="ver">Ver mais</button>
          </td>
        </tr>
      `;
    }).join("");
  }

  function updatePaginationUI(total, totalPages, pageCount, startIndex) {
    const from = total ? startIndex + 1 : 0;
    const to = total ? Math.min(startIndex + pageCount, total) : 0;

    if (pagInfo) pagInfo.textContent = `Mostrando ${from}–${to} de ${total} registro(s)`;

    const resumo = total ? `Encontrados ${total} registro(s).` : "Nenhum registro encontrado.";
    if (lblResumo) lblResumo.textContent = resumo;

    const lblResumoCards = $("#lblResumoCards");
    if (lblResumoCards) lblResumoCards.textContent = resumo;

    if (pagAtualEl) pagAtualEl.textContent = String(total ? currentPage : 1);
    if (pagTotalEl) pagTotalEl.textContent = String(total ? totalPages : 1);

    [btnPagFirst, btnPagPrev].forEach((btn) => btn && (btn.disabled = currentPage <= 1 || !total));
    [btnPagNext, btnPagLast].forEach((btn) => btn && (btn.disabled = currentPage >= totalPages || !total));
  }

  function renderPagina() {
    const ordenadas = ordenarRows(allRows);
    const total = ordenadas.length;
    const totalPages = total ? Math.ceil(total / PAGE_SIZE) : 1;

    currentPage = Math.max(1, Math.min(currentPage, totalPages));

    const start = (currentPage - 1) * PAGE_SIZE;
    const pageRows = ordenadas.slice(start, start + PAGE_SIZE);

    renderCards(pageRows);
    renderTabelaCompat(pageRows);
    updatePaginationUI(total, totalPages, pageRows.length, start);
  }

  function goToPage(where) {
    const total = allRows.length;
    const totalPages = total ? Math.ceil(total / PAGE_SIZE) : 1;

    if (where === "first") currentPage = 1;
    if (where === "prev") currentPage = Math.max(1, currentPage - 1);
    if (where === "next") currentPage = Math.min(totalPages, currentPage + 1);
    if (where === "last") currentPage = totalPages;

    renderPagina();
  }

  function buildFilterParams() {
    const p = new URLSearchParams();

    const qVal = valFiltro(inpBusca?.value);
    if (qVal) p.set("q", qVal);

    if (selProf && isInput(selProf) && inpProfId) {
      const profIdVal = valFiltro(inpProfId.value);
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
    return `/registros/api/list${qs ? "?" + qs : ""}`;
  }

  async function listar() {
    try {
      const resp = await fetch(buildListURL());
      const rows = await resp.json();

      allRows = Array.isArray(rows) ? rows : [];
      currentPage = 1;
      renderPagina();
    } catch (err) {
      console.error("[registros] Erro ao listar:", err);
      allRows = [];
      renderCards([]);
      renderTabelaCompat([]);
      if (lblResumo) lblResumo.textContent = "Erro ao carregar registros.";
      updatePaginationUI(0, 1, 0, 0);
    }
  }

  function limpar() {
    frm && frm.reset();
    if (inpProfId) inpProfId.value = "";
    if (sugBox) {
      sugBox.classList.add("hide");
      sugBox.innerHTML = "";
    }

    aplicarCompetenciaPadrao();

    if (selOrdem) selOrdem.value = "data_desc";

    lastModalRowObj = null;
    listar();
  }

  function exportarXLSX() {
    const p = buildFilterParams();
    const qs = p.toString();
    window.location.href = `/registros/exportar_xlsx${qs ? "?" + qs : ""}`;
  }

  function exportarEvolucoesPDF({ apenasPaciente = false } = {}) {
    const p = buildFilterParams();

    if (apenasPaciente && lastModalRowObj) {
      const pid = lastModalRowObj.paciente_id ?? lastModalRowObj.pacienteId ?? "";
      if (String(pid).trim()) p.set("paciente_id", String(pid).trim());
    }

    const qs = p.toString();
    window.open(`/registros/evolucoes/pdf${qs ? "?" + qs : ""}`, "_blank");
  }

  async function acFetch(q) {
    const resp = await fetch(`/atendimentos/api/profissionais_sugestao?q=${encodeURIComponent(q)}`);
    const data = await resp.json();
    return Array.isArray(data) ? data : [];
  }

  function initProfAutocomplete() {
    if (!selProf || !isInput(selProf) || !inpProfId || !sugBox) return false;

    const acHide = () => {
      sugBox.classList.add("hide");
      sugBox.innerHTML = "";
    };

    const acRender = (items) => {
      if (!items.length) {
        sugBox.innerHTML = `<div class="prof-sug empty">Nenhum resultado</div>`;
        sugBox.classList.remove("hide");
        return;
      }

      sugBox.innerHTML = items.map((p) => {
        const id = p.id != null ? String(p.id) : "";
        const nome = (p.nome || "").trim() || (id ? `ID ${id}` : "Sem nome");
        const cbo = (p.cbo || "").trim();
        const label = cbo ? `${nome} (${cbo})` : nome;

        return `
          <button type="button" class="prof-sug" data-id="${escapeAttr(id)}" data-label="${escapeAttr(label)}">
            <strong>${escapeHtml(nome)}</strong>${cbo ? ` <span class="muted">(CBO ${escapeHtml(cbo)})</span>` : ""}
          </button>
        `;
      }).join("");

      sugBox.classList.remove("hide");
    };

    const onInput = debounce(async () => {
      const q = String(selProf.value || "").trim();
      inpProfId.value = "";

      if (q.length < 3) {
        acHide();
        return;
      }

      try {
        acRender(await acFetch(q));
      } catch {
        acHide();
      }
    }, 220);

    selProf.addEventListener("input", onInput);

    selProf.addEventListener("keydown", (e) => {
      if (e.key === "Escape") acHide();
      if (e.key === "Enter") {
        e.preventDefault();
        acHide();
        listar();
      }
    });

    sugBox.addEventListener("click", (e) => {
      const btn = e.target.closest(".prof-sug[data-id]");
      if (!btn) return;

      selProf.value = btn.getAttribute("data-label") || "";
      inpProfId.value = btn.getAttribute("data-id") || "";
      acHide();
      listar();
    });

    document.addEventListener("click", (e) => {
      const wrap = document.getElementById("f_prof_wrap");
      if (wrap && wrap.contains(e.target)) return;
      acHide();
    });

    return true;
  }

  async function carregarProfissionaisSelectLegado() {
    if (!selProf || !isSelect(selProf)) return;

    try {
      const resp = await fetch("/atendimentos/api/profissionais");
      const data = await resp.json();

      if (!Array.isArray(data) || !data.length) return;

      selProf.innerHTML = `<option value="">Todos</option>`;

      data.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id != null ? String(p.id) : "";
        opt.textContent = p.cbo ? `${p.nome || `ID ${p.id}`} (${p.cbo})` : (p.nome || `ID ${p.id}`);
        selProf.appendChild(opt);
      });
    } catch (e) {
      console.warn("[registros] Não foi possível carregar profissionais:", e);
    }
  }

  function initModalTabs() {
    if (!dlg) return;

    dlg.querySelectorAll(".mr-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const tabName = tab.getAttribute("data-tab");
        if (tabName) setModalTab(tabName);
      });
    });
  }

  function initCopyButtons() {
    function bind(btn, target, originalText) {
      if (!btn || !target) return;

      btn.addEventListener("click", async () => {
        const txt = (target.textContent || "").trim();

        if (!txt || txt === "—" || txt === "Conteúdo restrito.") {
          btn.textContent = "⚠️ Sem texto";
          setTimeout(() => (btn.textContent = originalText), 1200);
          return;
        }

        try {
          await navigator.clipboard.writeText(txt);
          btn.textContent = "✅ Copiado";
        } catch {
          btn.textContent = "⚠️ Falhou";
        }

        setTimeout(() => (btn.textContent = originalText), 1200);
      });
    }

    bind(mrBtnCopyEvo, mrEvolucao, "📎 Copiar");
    bind(mrBtnCopyOculta, mrEvolucaoOculta, "📎 Copiar");
  }

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

  [selStatus, selSexo, inpDataIni, inpDataFim].forEach((el) => {
    el?.addEventListener("change", listar);
  });

  if (selProf && isSelect(selProf)) {
    selProf.addEventListener("change", listar);
  }

  inpBusca?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      listar();
    }
  });

  tbl?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act='ver']");
    if (!btn) return;

    const tr = btn.closest("tr");
    const obj = decodeDataRow(tr?.getAttribute("data-row") || "{}");
    openModalFromObj(obj);
  });

  document.addEventListener("click", (e) => {
    const cardBtn = e.target.closest("[data-act='ver-card']");
    if (cardBtn) {
      const card = cardBtn.closest(".registro-card");
      const obj = decodeDataRow(card?.getAttribute("data-row") || "{}");
      openModalFromObj(obj);
      return;
    }

    if (!dlg) return;
    if (e.target.closest("[value='close']")) {
      if (typeof dlg.close === "function") dlg.close();
      else dlg.removeAttribute("open");
    }
  });

  [
    [btnPagFirst, "first"],
    [btnPagPrev, "prev"],
    [btnPagNext, "next"],
    [btnPagLast, "last"],
  ].forEach(([btn, where]) => {
    btn?.addEventListener("click", (e) => {
      e.preventDefault();
      goToPage(where);
    });
  });

  document.addEventListener("DOMContentLoaded", () => {
    const btnBPAI = $("#btnExportBPAI");
    btnBPAI?.addEventListener("click", () => {
      const qs = buildFilterParams().toString();
      window.location.href = `/registros/exportar_bpai_xlsx${qs ? "?" + qs : ""}`;
    });

    const btnEvoGeral = $("#btnExportarEvoGeralPdf");
    btnEvoGeral?.addEventListener("click", (e) => {
      e.preventDefault();
      exportarEvolucoesPDF({ apenasPaciente: false });
    });

    const btnEvoPaciente = $("#btnExportarEvoPacientePdf");
    btnEvoPaciente?.addEventListener("click", (e) => {
      e.preventDefault();
      exportarEvolucoesPDF({ apenasPaciente: true });
    });
  });

  (async () => {
    ensureCardsUI();
    aplicarCompetenciaPadrao();
    initModalTabs();
    initCopyButtons();

    const okAC = initProfAutocomplete();
    if (!okAC) await carregarProfissionaisSelectLegado();

    listar();
  })();
})();