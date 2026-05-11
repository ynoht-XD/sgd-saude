// ===========================================================
// PTS — JS ÚNICO MODERNO
// Arquivo: pts/static/js/pts.js
// ===========================================================

(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const on = (el, ev, fn, opts) => {
    if (el) el.addEventListener(ev, fn, opts);
  };

  const safeTrim = (v) => (v ?? "").toString().trim();

  const debounce = (fn, ms = 250) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  };

  const toast = (msg, type = "info") => {
    let wrap = $("#ptsToastWrap");

    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "ptsToastWrap";
      wrap.style.cssText = `
        position:fixed;
        right:18px;
        bottom:18px;
        z-index:9999;
        display:grid;
        gap:10px;
        max-width:min(380px, calc(100vw - 28px));
      `;
      document.body.appendChild(wrap);
    }

    const el = document.createElement("div");
    el.textContent = msg;
    el.style.cssText = `
      padding:12px 14px;
      border-radius:16px;
      font-weight:800;
      color:#0f172a;
      background:#fff;
      border:1px solid #e2e8f0;
      box-shadow:0 18px 42px rgba(15,23,42,.16);
    `;

    if (type === "success") {
      el.style.background = "#d1fae5";
      el.style.borderColor = "rgba(16,185,129,.35)";
      el.style.color = "#065f46";
    }

    if (type === "error") {
      el.style.background = "#fee2e2";
      el.style.borderColor = "rgba(239,68,68,.35)";
      el.style.color = "#991b1b";
    }

    wrap.appendChild(el);

    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(6px)";
      el.style.transition = ".2s ease";
      setTimeout(() => el.remove(), 220);
    }, 2800);
  };

  const escapeHTML = (v) =>
    safeTrim(v)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const buildURL = (base, params = {}) => {
    const u = new URL(base, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && safeTrim(v) !== "") {
        u.searchParams.set(k, v);
      }
    });
    return u.toString();
  };

  async function safeJSON(url) {
    const r = await fetch(url, {
      headers: {
        "X-Requested-With": "fetch",
        "Accept": "application/json",
      },
    });

    if (!r.ok) {
      console.warn("[PTS] Requisição falhou:", r.status, url);
      return null;
    }

    return r.json();
  }

  function hideBox(box) {
    if (!box) return;

    box.innerHTML = "";
    box.style.display = "none";

    const field = box.closest(".field");

    if (field) {
      field.classList.remove("autocomplete-open");
    }
  }

  function showLoading(box, text = "Buscando...") {
    if (!box) return;
    box.innerHTML = `<div class="sugg-item"><div><div class="title">${text}</div></div></div>`;
    box.style.display = "block";

    const field = box.closest(".field");

    if (field) {
      field.classList.add("autocomplete-open");
    }
  }

  function normalizeDate(v) {
    const s = safeTrim(v);
    if (!s) return { iso: "", br: "" };

    if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
      const iso = s.slice(0, 10);
      const [y, m, d] = iso.split("-");
      return { iso, br: `${d}/${m}/${y}` };
    }

    const br = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
    if (br) {
      const [, d, m, y] = br;
      return { iso: `${y}-${m}-${d}`, br: `${d}/${m}/${y}` };
    }

    return { iso: "", br: s };
  }

  // ===========================================================
  // CONFIG
  // ===========================================================

  const api = $("#ptsApi");

  const urlSugestoesPaciente =
    api?.dataset?.urlSugestoes ||
    "/atendimentos/api/sugestoes_pacientes";

  const urlProfissionais =
    api?.dataset?.urlProfissionais ||
    "/pts/api/profissionais";

  const urlProfissionaisLegacy =
    api?.dataset?.urlProfissionaisLegacy ||
    "/buscar_profissionais_pec";

  const formCadastro = $("#formPTS");
  const isCadastro = !!formCadastro;

  const isLista =
    !!$("#formPtsFiltros") ||
    !!$("#tblPtsLista") ||
    document.body?.classList?.contains("pts-lista");

  // ===========================================================
  // CADASTRO
  // ===========================================================

  if (isCadastro) {
    const nome = $("#nome_paciente");
    const boxPaciente = $("#sugestoes_paciente");

    const hidPacienteId = $("#paciente_id");

    const iNascHidden = $("#data_nascimento");
    const iNascVis = $("#data_nascimento_visivel");
    const iPront = $("#prontuario");
    const iCns = $("#cns");
    const iMae = $("#nome_mae");
    const iSexo = $("#sexo");
    const iRaca = $("#raca");
    const iEnd = $("#endereco");
    const iNum = $("#numero");
    const iBairro = $("#bairro");
    const iCep = $("#cep");
    const iCpf = $("#cpf");
    const indicadorPaciente = $("#indicadorPaciente");

    const btnLimpar = $("#btnLimpar");
    const btnImprimir = $("#btnImprimir");

    const inpPart = $("#participantesInput");
    const boxPart = $("#participantesSugestoes");
    const chipsWrap = $("#chipsParticipantes");
    const hiddenIds = $("#participantesIds");

    const listaLegacy = $("#lista-participantes");
    const btnAddLegacy = $("#btnAddParticipante");

    let pacienteSelecionado = null;
    let PARTICIPANTES = [];
    let lastProfItems = [];
    let PROFISSIONAIS_LEGACY = [];

    function limparPaciente() {
      pacienteSelecionado = null;

      if (hidPacienteId) hidPacienteId.value = "";
      if (iNascHidden) iNascHidden.value = "";
      if (iNascVis) iNascVis.value = "";
      if (iPront) iPront.value = "";
      if (iCns) iCns.value = "";
      if (iMae) iMae.value = "";
      if (iSexo) iSexo.value = "";
      if (iRaca) iRaca.value = "";
      if (iEnd) iEnd.value = "";
      if (iNum) iNum.value = "";
      if (iBairro) iBairro.value = "";
      if (iCep) iCep.value = "";
      if (iCpf) iCpf.value = "";

      if (indicadorPaciente) {
        indicadorPaciente.textContent = "Nenhum paciente selecionado";
        indicadorPaciente.classList.remove("ok");
      }
    }

    async function buscarPacientes(q) {
      const data = await safeJSON(buildURL(urlSugestoesPaciente, { termo: q }));
      return Array.isArray(data) ? data : (data?.items || data?.results || []);
    }

    function preencherPaciente(p) {
      if (!p) return;

      pacienteSelecionado = {
        id: p.id ? String(p.id) : "",
        nome: safeTrim(p.nome),
      };

      if (nome) nome.value = p.nome || "";

      const data = normalizeDate(p.nascimento);
      if (iNascHidden) iNascHidden.value = data.iso;
      if (iNascVis) iNascVis.value = data.br;

      if (iPront) iPront.value = p.prontuario || "";
      if (iCns) iCns.value = p.cns || "";
      if (iMae) iMae.value = p.mae || p.nome_mae || "";
      if (iSexo) iSexo.value = p.sexo || "";
      if (iRaca) iRaca.value = p.raca || "";
      if (iEnd) iEnd.value = p.logradouro || p.endereco || "";
      if (iNum) iNum.value = p.numero || "";
      if (iBairro) iBairro.value = p.bairro || "";
      if (iCep) iCep.value = p.cep || "";
      if (iCpf) iCpf.value = p.cpf || "";

      if (hidPacienteId) hidPacienteId.value = p.id ? String(p.id) : "";

      if (indicadorPaciente) {
        indicadorPaciente.textContent = p.nome
          ? `Paciente selecionado: ${p.nome}`
          : "Paciente selecionado";
        indicadorPaciente.classList.add("ok");
      }

      hideBox(boxPaciente);
      toast("Paciente selecionado.", "success");
    }

    function renderSugestoesPaciente(items) {
      if (!boxPaciente) return;

      boxPaciente.innerHTML = "";

      if (!items.length) {
        hideBox(boxPaciente);
        return;
      }

      items.forEach((p) => {
        const div = document.createElement("div");
        div.className = "sugg-item";
        div.setAttribute("role", "option");

        const nomeP = escapeHTML(p.nome || "Sem nome");
        const nasc = escapeHTML(p.nascimento || "");
        const pront = escapeHTML(p.prontuario || "");
        const cid = escapeHTML(p.cid || "");
        const cpf = escapeHTML(p.cpf || "");

        div.innerHTML = `
          <div>
            <div class="title">${nomeP}</div>
            <div class="sub">
              ${nasc ? `Nasc.: ${nasc}` : ""}
              ${pront ? ` • Pront.: ${pront}` : ""}
              ${cid ? ` • CID: ${cid}` : ""}
              ${cpf ? ` • CPF: ${cpf}` : ""}
            </div>
          </div>
          <span class="tag">Selecionar</span>
        `;

        div.addEventListener("click", () => preencherPaciente(p));
        boxPaciente.appendChild(div);
      });

      boxPaciente.style.display = "block";

      const field = boxPaciente.closest(".field");

      if (field) {
        field.classList.add("autocomplete-open");
      }
    }

    const onBuscaPaciente = debounce(async () => {
      if (!nome || !boxPaciente) return;

      const q = safeTrim(nome.value);
      hideBox(boxPaciente);

      if (q.length < 3) return;

      showLoading(boxPaciente, "Buscando pacientes...");

      try {
        const items = await buscarPacientes(q);
        renderSugestoesPaciente(items);
      } catch (e) {
        console.error("[PTS] erro ao buscar pacientes:", e);
        hideBox(boxPaciente);
        toast("Erro ao buscar pacientes.", "error");
      }
    }, 260);

    on(nome, "input", () => {
      const digitado = safeTrim(nome.value);

      if (
        pacienteSelecionado &&
        digitado &&
        digitado !== pacienteSelecionado.nome
      ) {
        limparPaciente();
      }

      onBuscaPaciente();
    });

    on(document, "click", (e) => {
      if (!boxPaciente || !nome) return;
      if (!boxPaciente.contains(e.target) && e.target !== nome) {
        hideBox(boxPaciente);
      }
    });

    // ===========================================================
    // PARTICIPANTES
    // ===========================================================

    async function buscarProfissionais(q) {
      const data = await safeJSON(buildURL(urlProfissionais, { q }));
      const items = data?.items || data?.results || data;
      return Array.isArray(items) ? items : [];
    }

    function syncHiddenParticipantes() {
      if (hiddenIds) {
        hiddenIds.value = PARTICIPANTES.map((p) => p.id).join(",");
      }
    }

    function renderChips() {
      if (!chipsWrap) return;

      chipsWrap.innerHTML = "";

      if (!PARTICIPANTES.length) {
        chipsWrap.innerHTML = `<span class="muted">Sem participantes adicionados.</span>`;
        syncHiddenParticipantes();
        return;
      }

      PARTICIPANTES.forEach((p) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.title = "Remover participante";

        chip.innerHTML = `
          <span class="chip-name">${escapeHTML(p.nome)}</span>
          ${p.funcao ? `<span class="chip-sub">${escapeHTML(p.funcao)}</span>` : ""}
          ${p.cbo ? `<span class="chip-sub">CBO ${escapeHTML(p.cbo)}</span>` : ""}
          <span class="chip-x">×</span>
        `;

        chip.addEventListener("click", () => {
          PARTICIPANTES = PARTICIPANTES.filter((x) => x.id !== p.id);
          renderChips();
        });

        chipsWrap.appendChild(chip);
      });

      syncHiddenParticipantes();
    }

    function addParticipanteFromItem(item) {
      const id = Number(item?.id);
      const nomeP = safeTrim(item?.nome);
      const cboP = safeTrim(item?.cbo);
      const funcP = safeTrim(item?.ocupacao || item?.funcao || item?.funcao_sugerida);

      if (!id || !nomeP) return;

      if (PARTICIPANTES.some((x) => x.id === id)) {
        toast("Esse profissional já foi adicionado.", "info");
        return;
      }

      PARTICIPANTES.push({
        id,
        nome: nomeP,
        cbo: cboP,
        funcao: funcP,
      });

      renderChips();

      if (inpPart) inpPart.value = "";
      hideBox(boxPart);
      inpPart?.focus();

      toast("Participante adicionado.", "success");
    }

    function renderSugestoesProfissionais(items) {
      if (!boxPart) return;

      boxPart.innerHTML = "";
      lastProfItems = Array.isArray(items) ? items : [];

      if (!lastProfItems.length) {
        hideBox(boxPart);
        return;
      }

      lastProfItems.forEach((p) => {
        const id = Number(p.id);
        const nomeP = safeTrim(p.nome);
        const cboP = safeTrim(p.cbo);
        const funcaoP = safeTrim(p.ocupacao || p.funcao || p.funcao_sugerida);

        if (!id || !nomeP) return;

        const already = PARTICIPANTES.some((x) => x.id === id);

        const div = document.createElement("div");
        div.className = "sugg-item";

        div.innerHTML = `
          <div>
            <div class="title">
              ${escapeHTML(nomeP)} ${already ? "<small>(já adicionado)</small>" : ""}
            </div>
            <div class="sub">
              ${funcaoP ? `Função: ${escapeHTML(funcaoP)}` : ""}
              ${funcaoP && cboP ? " • " : ""}
              ${cboP ? `CBO: ${escapeHTML(cboP)}` : ""}
            </div>
          </div>
          <span class="tag">${already ? "OK" : "Add"}</span>
        `;

        div.addEventListener("click", () => {
          if (!already) addParticipanteFromItem(p);
        });

        boxPart.appendChild(div);
      });

      boxPart.style.display = "block";

      const field = boxPart.closest(".field");

      if (field) {
        field.classList.add("autocomplete-open");
      }
    }

    const onBuscaProfissional = debounce(async () => {
      if (!inpPart || !boxPart) return;

      const q = safeTrim(inpPart.value);
      hideBox(boxPart);

      if (q.length < 3) return;

      showLoading(boxPart, "Buscando profissionais...");

      try {
        const items = await buscarProfissionais(q);
        renderSugestoesProfissionais(items);
      } catch (e) {
        console.error("[PTS] erro ao buscar profissionais:", e);
        hideBox(boxPart);
        toast("Erro ao buscar profissionais.", "error");
      }
    }, 240);

    on(inpPart, "input", onBuscaProfissional);

    on(inpPart, "keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const first = lastProfItems.find(
          (p) => !PARTICIPANTES.some((x) => x.id === Number(p.id))
        );
        if (first) addParticipanteFromItem(first);
      }

      if (e.key === "Escape") hideBox(boxPart);
    });

    on(document, "click", (e) => {
      if (!boxPart || !inpPart) return;
      if (!boxPart.contains(e.target) && e.target !== inpPart) {
        hideBox(boxPart);
      }
    });

    // ===========================================================
    // LEGACY OPCIONAL
    // ===========================================================

    async function carregarProfissionaisLegacy() {
      try {
        const data = await safeJSON(urlProfissionaisLegacy);
        PROFISSIONAIS_LEGACY = Array.isArray(data) ? data : [];
      } catch {
        PROFISSIONAIS_LEGACY = [];
      }
    }

    function mkSelect(opts, { name, placeholder }) {
      const sel = document.createElement("select");
      sel.name = name;
      sel.required = true;
      sel.className = "form-select";
      sel.innerHTML = `<option value="">${escapeHTML(placeholder || "Selecione")}</option>`;

      opts.forEach((o) => {
        const op = document.createElement("option");
        op.value = o.value;
        op.textContent = o.label;
        sel.appendChild(op);
      });

      return sel;
    }

    function addParticipanteRowLegacy(prefill) {
      if (!listaLegacy) return;

      const row = document.createElement("div");
      row.className = "participant-row";

      const nomes = PROFISSIONAIS_LEGACY.map((p) => ({
        value: p.nome,
        label: p.nome,
      }));

      const funcoes = PROFISSIONAIS_LEGACY.map((p) => ({
        value: p.funcao || p.cbo || "",
        label: p.funcao || p.cbo || "",
      }));

      const sNome = mkSelect(nomes, {
        name: "participantes_nome[]",
        placeholder: "Profissional",
      });

      const sFunc = mkSelect(funcoes, {
        name: "participantes_cbo[]",
        placeholder: "Função/CBO",
      });

      if (prefill?.nome) sNome.value = prefill.nome;
      if (prefill?.funcao) sFunc.value = prefill.funcao;

      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "btn danger";
      btnDel.textContent = "Remover";
      btnDel.addEventListener("click", () => row.remove());

      row.appendChild(sNome);
      row.appendChild(sFunc);
      row.appendChild(btnDel);
      listaLegacy.appendChild(row);
    }

    on(btnAddLegacy, "click", async () => {
      if (!listaLegacy) return;

      if (!PROFISSIONAIS_LEGACY.length) {
        toast("Carregando profissionais...", "info");
        await carregarProfissionaisLegacy();
      }

      addParticipanteRowLegacy();
    });

    // ===========================================================
    // BOTÕES / VALIDAÇÃO
    // ===========================================================

    on(btnLimpar, "click", () => {
      formCadastro.reset();

      limparPaciente();

      if (listaLegacy) listaLegacy.innerHTML = "";

      PARTICIPANTES = [];
      lastProfItems = [];

      renderChips();

      hideBox(boxPaciente);
      hideBox(boxPart);

      nome?.focus();

      toast("Formulário limpo.", "success");
    });

    on(btnImprimir, "click", () => window.print());

    on(formCadastro, "submit", (e) => {
      const pid = safeTrim(hidPacienteId?.value);

      if (!pid) {
        e.preventDefault();
        toast("Selecione um paciente na lista antes de salvar.", "error");
        nome?.focus();
        return;
      }

      const obrigatorios = [
        "nome_paciente",
        "localizacao_territorial",
        "diagnostico_funcional",
      ];

      const faltando = obrigatorios.filter((name) => {
        const el = formCadastro.elements[name];
        return !el || !safeTrim(el.value);
      });

      if (faltando.length) {
        e.preventDefault();
        toast("Preencha os campos obrigatórios do PTS.", "error");
        formCadastro.elements[faltando[0]]?.focus();
        return;
      }

      syncHiddenParticipantes();
    });

    (async function initCadastro() {
      renderChips();

      if (btnAddLegacy && listaLegacy) {
        await carregarProfissionaisLegacy();
      }
    })();
  }

  // ===========================================================
  // LISTA / VISUALIZAR
  // ===========================================================

  if (isLista) {
    const btnClear = $("#btnPtsLimparFiltros");
    const btnGoTop = $("#btnPtsTopo");

    on(btnClear, "click", (e) => {
      e.preventDefault();
      window.location.href = window.location.pathname;
    });

    on(btnGoTop, "click", (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    $$("input[name='competencia']").forEach((el) => {
      on(el, "input", () => {
        let v = el.value.replace(/[^\d-]/g, "");

        if (/^\d{6}$/.test(v)) {
          v = `${v.slice(0, 4)}-${v.slice(4)}`;
        }

        if (v.length > 7) v = v.slice(0, 7);

        el.value = v;
      });
    });
  }
})();