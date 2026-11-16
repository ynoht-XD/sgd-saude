// registros/static/js/registros.js
(function () {
  "use strict";

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
  const btnExportBPAI = $("#btnExportBPAI");
  const btnEvoGeral = $("#btnExportarEvoGeralPdf");
  const btnEvoPaciente = $("#btnExportarEvoPacientePdf");

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

  const cardsWrap = $("#cardsRegistros");
  const selOrdem = $("#f_ordem");

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
  const mrCidAtendimento = $("#mr_cid_atendimento");
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

  const PAGE_SIZE = 15;

  let allRows = [];
  let currentPage = 1;
  let lastModalRowObj = null;

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

    const iso = isoDate(s);

    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
      const [y, m, dia] = iso.split("-");
      return `${dia}/${m}/${y}`;
    }

    return s;
  }

  // "2026-11-10", "2026-11-10T00:00:00" ou "Tue, 10 Nov 2026 00:00:00 GMT" (formato que a API manda) -> "2026-11-10"
  function isoDate(v) {
    const s = String(v ?? "").trim();
    if (!s) return "";
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);

    const t = Date.parse(s);
    if (Number.isNaN(t)) return "";

    const d = new Date(t);   // a data vem a meia-noite GMT: usa os campos UTC para nao voltar um dia
    const p2 = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`;
  }

  function toDateNumber(v) {
    const s = isoDate(v);
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

  function decodeDataRow(raw) {
    try {
      return JSON.parse(String(raw || "{}").replaceAll("&quot;", '"'));
    } catch {
      return {};
    }
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
    const direct = pick(
      obj,
      ["profissional_nome", "profissional", "nome_profissional", "usuario_nome", "nome_usuario", "ag__profissional"],
      ""
    );

    if (direct && direct !== "—") return direct;

    const pid = obj.profissional_id ?? obj.prof_id ?? obj.id_profissional ?? obj.usuario_id ?? "";
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
    ]
      .map((v) => String(v || "").trim())
      .filter(Boolean);

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

  function evoOcultaInfo(obj) {
    const total = Number(obj.evo_oculta_total || 0);
    const visivel = Number(obj.evo_oculta_visivel || 0);
    const situacao = String(obj.evo_oculta_situacao || "sem_evolucao_oculta");
    const texto = String(obj.evolucoes_ocultas_visiveis || "").trim();

    if (situacao === "visivel" || visivel > 0) {
      return {
        tipo: "visivel",
        badge: "🔓 Restrita visível",
        titulo: "Evoluções restritas liberadas",
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
        badge: "🔒 Restrita",
        titulo: "Evoluções restritas",
        sub: "Existe evolução restrita neste atendimento, mas ela não está liberada para seu usuário/CBO.",
        pill: "Restrita",
        total,
        visivel,
        texto: "Conteúdo restrito.",
      };
    }

    return {
      tipo: "sem",
      badge: "🔘 Sem restrita",
      titulo: "Sem evolução restrita",
      sub: "Este atendimento não possui evolução restrita registrada.",
      pill: "Sem registro",
      total: 0,
      visivel: 0,
      texto: "—",
    };
  }

  function mapFill(obj, mapping) {
    mapping.forEach((m) => {
      const raw = pick(obj, m.keys, m.fallback ?? "—");
      const val = typeof m.fmt === "function" ? m.fmt(raw, obj) : raw;
      setText(m.el, val, m.fallback ?? "—");
    });
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

  function fillModalEvolucaoRestrita(obj) {
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
      { el: mrCidAtendimento, keys: ["cid_codigo"] },
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

    fillModalEvolucaoRestrita(obj);
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

  function tagStatusReg(label) {
    const l = String(label || "").toLowerCase();
    const cls = /pres|realiz|alta/.test(l) ? "acd-tag--ok" : /falt|[óo]bito|deslig/.test(l) ? "acd-tag--falta" : /just|remarc|admiss/.test(l) ? "acd-tag--alerta" : "";
    return label && label !== "—" ? `<span class="acd-tag ${cls}">${escapeHtml(label)}</span>` : "";
  }

  function renderCards(rows) {
    if (!cardsWrap) return;

    if (!rows || !rows.length) {
      cardsWrap.innerHTML = `<p class="acd-vazio">Nenhum registro encontrado.</p>`;
      return;
    }

    cardsWrap.innerHTML = rows.map((r, i) => {
      const aid = String(r.id ?? r.atendimento_id ?? `i${i}`);
      const paciente = pacienteNameFrom(r);
      const dtRaw = dataFrom(r);
      const dt = dtRaw ? fmtDataBR(dtRaw) : "—";
      const prof = profNameFrom(r);
      const statusLbl = normalizeStatusLabel(pick(r, ["status", "situacao", "comparecimento", "paciente_status", "pac__status"], ""));
      const cid = pick(r, ["pac__cid", "paciente_cid", "cid", "cid_principal", "cid10"], "");
      const cidAtend = pick(r, ["cid_codigo"], "");
      const just = String(pick(r, ["status_justificativa", "justificativa", "motivo"], "") || "").trim();
      const evo = String(pick(r, ["evolucao", "evolucao_texto", "observacao", "observacoes"], "") || "").trim();
      const procs = Array.isArray(r.__procs) ? r.__procs : [];
      const p1 = procs[0];
      const cbo = pick(r, ["profissional_cbo", "cbo_profissional", "cbo", "ag__prof_cbo"], "");
      const profCns = pick(r, ["profissional_cns", "cns_profissional"], "");
      const info = evoOcultaInfo(r);
      const pacId = r.paciente_id ?? "";
      const dataRow = JSON.stringify(r).replaceAll('"', "&quot;");

      const subProc = p1
        ? `${p1.codigo ? `<code>${escapeHtml(p1.codigo)}</code>` : ""}${escapeHtml(p1.procedimento)}${procs.length > 1 ? ` <span class="acd-mais">+${procs.length - 1} procedimento(s)</span>` : ""}`
        : `<span class="acd-mais">Sem procedimento registrado</span>`;

      const tags = [
        tagStatusReg(statusLbl),
        cidAtend ? `<span class="acd-tag acd-tag--info" title="CID do atendimento">CID ${escapeHtml(cidAtend)}</span>` : "",
        info.tipo === "visivel" ? `<span class="acd-tag acd-tag--info" title="${escapeAttr(info.sub)}">Evolução restrita liberada</span>` : "",
        info.tipo === "restrita" ? `<span class="acd-tag acd-tag--alerta" title="${escapeAttr(info.sub)}">Evolução restrita</span>` : "",
      ].filter(Boolean).join("");

      const procHtml = procs.length
        ? `<ul class="acd-lista-proc">${procs.map((p) => `<li>${p.codigo ? `<code>${escapeHtml(p.codigo)}</code>` : ""}<span>${escapeHtml(p.procedimento || "—")}</span></li>`).join("")}</ul>`
        : `<p class="acd-texto acd-texto--vazio">Nenhum procedimento registrado neste atendimento.</p>`;

      const restritaHtml = info.tipo === "sem" ? "" : `
        <div class="acd-bloco"><span class="acd-rot">Evolução restrita</span>
          ${info.tipo === "visivel"
            ? `<pre class="acd-texto">${escapeHtml(info.texto)}</pre>`
            : `<p class="acd-texto acd-texto--vazio">${escapeHtml(info.sub)}</p>`}
        </div>`;

      return `
        <article class="acd-item" data-aid="${escapeAttr(aid)}" data-row="${dataRow}">
          <button type="button" class="acd-head" id="acd-h-${escapeAttr(aid)}" aria-expanded="false" aria-controls="acd-p-${escapeAttr(aid)}">
            <span class="acd-col acd-col--data"><b>${escapeHtml(dt)}</b></span>
            <span class="acd-col acd-col--main">
              <span class="acd-titulo">${escapeHtml(paciente)}</span>
              <span class="acd-sub">${escapeHtml(prof)} · ${subProc}</span>
              ${tags ? `<span class="acd-tags">${tags}</span>` : ""}
            </span>
            <span class="acd-chevron" aria-hidden="true"></span>
          </button>

          <div class="acd-panel" id="acd-p-${escapeAttr(aid)}" role="region" aria-labelledby="acd-h-${escapeAttr(aid)}" hidden>
            <div class="acd-grid">
              <div class="acd-card">
                <span class="acd-rot">Profissional</span>
                <div class="acd-val">${escapeHtml(prof)}<small>${cbo ? `CBO ${escapeHtml(cbo)}` : "CBO não informado"}${profCns ? ` · CNS ${escapeHtml(profCns)}` : ""}</small></div>
              </div>
              <div class="acd-card">
                <span class="acd-rot">Diagnóstico (CID do atendimento)</span>
                <div class="acd-val">${cidAtend ? `<span class="acd-cid">${escapeHtml(cidAtend)}</span>` : `<span class="acd-val--vazio">Não informado</span>`}${cid ? `<small>CID do cadastro: ${escapeHtml(cid)}</small>` : ""}</div>
              </div>
              <div class="acd-card">
                <span class="acd-rot">Situação</span>
                <div class="acd-val">${tagStatusReg(statusLbl) || `<span class="acd-val--vazio">—</span>`}${just ? `<small>${escapeHtml(just)}</small>` : ""}</div>
              </div>
              <div class="acd-card">
                <span class="acd-rot">Paciente</span>
                <div class="acd-val">${escapeHtml(paciente)}<small>CNS ${escapeHtml(cnsFrom(r))}</small></div>
              </div>
            </div>

            <div class="acd-bloco"><span class="acd-rot">Procedimentos realizados</span>${procHtml}</div>

            <div class="acd-bloco"><span class="acd-rot">Evolução</span>
              ${evo ? `<pre class="acd-texto">${escapeHtml(evo)}</pre>` : `<p class="acd-texto acd-texto--vazio">Sem evolução registrada.</p>`}
            </div>
            ${restritaHtml}

            <div class="acd-acoes">
              <button type="button" class="acd-link" data-act="ver-card">Ficha completa (paciente e evolução restrita)</button>
              ${pacId ? `<a class="acd-link" href="/atendimentos/historico?paciente_id=${encodeURIComponent(pacId)}&paciente_nome=${encodeURIComponent(paciente)}">Histórico do paciente</a>` : ""}
            </div>
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

    if (pagAtualEl) pagAtualEl.textContent = String(total ? currentPage : 1);
    if (pagTotalEl) pagTotalEl.textContent = String(total ? totalPages : 1);

    [btnPagFirst, btnPagPrev].forEach((btn) => {
      if (btn) btn.disabled = currentPage <= 1 || !total;
    });

    [btnPagNext, btnPagLast].forEach((btn) => {
      if (btn) btn.disabled = currentPage >= totalPages || !total;
    });
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

  // A API devolve UMA linha por procedimento (JOIN): um atendimento com 3 procedimentos vinha 3 vezes. Aqui vira 1 item com a lista
  // de procedimentos, e a data fica em ISO (formatacao e ordenacao por data dependiam disso).
  function agruparPorAtendimento(rows) {
    const mapa = new Map();
    const saida = [];

    rows.forEach((r) => {
      const dt = isoDate(dataFrom(r));
      const proc = String(pick(r, ["procedimento", "procedimento_nome", "procedimento_desc", "ap_procedimento"], "") || "").trim();
      const cod = String(pick(r, ["codigo_sigtap", "cod_sigtap", "sigtap", "ap_codigo_sigtap"], "") || "").trim();
      const chave = r.id ?? r.atendimento_id ?? null;

      let item = chave != null ? mapa.get(chave) : null;
      if (!item) {
        item = { ...r, ...(dt ? { data_atendimento: dt } : {}), __procs: [] };
        if (chave != null) mapa.set(chave, item);
        saida.push(item);
      }

      if ((proc || cod) && !item.__procs.some((x) => x.procedimento === proc && x.codigo === cod)) {
        item.__procs.push({ procedimento: proc, codigo: cod });
      }
    });

    return saida;
  }

  async function listar() {
    try {
      const resp = await fetch(buildListURL(), { credentials: "same-origin" });
      const rows = await resp.json();

      allRows = agruparPorAtendimento(Array.isArray(rows) ? rows : []);
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
    frm?.reset();

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

  function exportarBPAI() {
    const p = buildFilterParams();
    const qs = p.toString();
    window.location.href = `/registros/exportar_bpai_xlsx${qs ? "?" + qs : ""}`;
  }

  function abrirPdf(urlBase, params) {
    const qs = params.toString();
    window.open(`${urlBase}${qs ? "?" + qs : ""}`, "_blank");
  }

  function exportarEvolucoesGeraisPDF() {
    const p = buildFilterParams();

    abrirPdf("/registros/evolucoes/pdf", p);
  }

  function exportarEvolucoesRestritasPDF() {
    const p = buildFilterParams();

    if (lastModalRowObj) {
      const pid =
        lastModalRowObj.paciente_id ??
        lastModalRowObj.pacienteId ??
        lastModalRowObj.pac__id ??
        "";

      if (String(pid).trim()) {
        p.set("paciente_id", String(pid).trim());
      }
    }

    abrirPdf("/registros/evolucoes-restritas/pdf", p);
  }

  async function acFetch(q) {
    const resp = await fetch(`/atendimentos/api/profissionais_sugestao?q=${encodeURIComponent(q)}`, {
      credentials: "same-origin",
    });

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
            <strong>${escapeHtml(nome)}</strong>
            ${cbo ? `<span class="muted">(CBO ${escapeHtml(cbo)})</span>` : ""}
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
      const wrap = $("#f_prof_wrap");
      if (wrap && wrap.contains(e.target)) return;
      acHide();
    });

    return true;
  }

  async function carregarProfissionaisSelectLegado() {
    if (!selProf || !isSelect(selProf)) return;

    try {
      const resp = await fetch("/atendimentos/api/profissionais", {
        credentials: "same-origin",
      });

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

  function bindEvents() {
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

    btnExportBPAI?.addEventListener("click", (e) => {
      e.preventDefault();
      exportarBPAI();
    });

    btnEvoGeral?.addEventListener("click", (e) => {
      e.preventDefault();
      exportarEvolucoesGeraisPDF();
    });

    btnEvoPaciente?.addEventListener("click", (e) => {
      e.preventDefault();
      exportarEvolucoesRestritasPDF();
    });

    [selStatus, selSexo, inpDataIni, inpDataFim].forEach((el) => {
      el?.addEventListener("change", listar);
    });

    if (selProf && isSelect(selProf)) {
      selProf.addEventListener("change", listar);
    }

    selOrdem?.addEventListener("change", () => {
      currentPage = 1;
      renderPagina();
    });

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
      const head = e.target.closest("#cardsRegistros .acd-head");

      if (head) {
        const item = head.closest(".acd-item");
        const painel = item?.querySelector(".acd-panel");
        if (painel) {
          const abrir = head.getAttribute("aria-expanded") !== "true";
          head.setAttribute("aria-expanded", abrir ? "true" : "false");
          painel.hidden = !abrir;
          item.classList.toggle("is-aberto", abrir);
        }
        return;
      }

      const cardBtn = e.target.closest("[data-act='ver-card']");

      if (cardBtn) {
        const card = cardBtn.closest(".acd-item");
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
  }

  async function boot() {
    aplicarCompetenciaPadrao();
    initModalTabs();
    initCopyButtons();
    bindEvents();

    const okAC = initProfAutocomplete();
    if (!okAC) await carregarProfissionaisSelectLegado();

    listar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();