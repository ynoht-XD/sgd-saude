// ===========================================================
// PTS — JS ÚNICO (Cadastro + Visualizar/Lista)
// Arquivo: pts/static/js/pts.js
//
// ✅ Cadastro (pts.html)
// - Autocomplete paciente (endpoint existente)
// - Preenche campos e grava #paciente_id (obrigatório)
// - Participantes (recomendado): autocomplete + chips + hidden ids
// - Profissionais: só busca a partir do 3º caractere
// - Mostra FUNÇÃO + CBO nas sugestões e chips
//
// ✅ Visualizar/Lista (pts_visualizar.html)
// - UX: limpar filtros e ir ao topo (se existir)
//
// ===========================================================
(() => {
  // ---------------------------
  // Helpers
  // ---------------------------
  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const on = (el, ev, fn, opts) => el && el.addEventListener(ev, fn, opts);

  const debounce = (fn, ms = 220) => {
    let t;
    return (...a) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...a), ms);
    };
  };

  function safeTrim(v) {
    return (v ?? "").toString().trim();
  }

  function toISOFromBRorISO(d) {
    const s = safeTrim(d);
    if (!s) return { iso: "", vis: "" };

    // ISO YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      const [Y, M, D] = s.split("-");
      return { iso: s, vis: `${D}/${M}/${Y}` };
    }

    // BR DD/MM/YYYY
    const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (m) {
      const [, D, M, Y] = m;
      return { iso: `${Y}-${M}-${D}`, vis: `${D}/${M}/${Y}` };
    }

    return { iso: "", vis: s };
  }

  function buildURL(base, params = {}) {
    const u = new URL(base, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") {
        u.searchParams.set(k, v);
      }
    });
    return u.toString();
  }

  async function safeJSON(url) {
    const r = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!r.ok) return null;
    return r.json();
  }

  function hideBox(box) {
    if (!box) return;
    box.innerHTML = "";
    box.style.display = "none";
  }

  // ---------------------------
  // Config (data-attrs)
  // ---------------------------
  const api = $("#ptsApi");

  // Pacientes (autocomplete) — endpoint atendimentos
  const urlSugestoesPaciente =
    api?.dataset?.urlSugestoes ||
    "/atendimentos/api/sugestoes_pacientes"; // ?termo=

  // Profissionais (autocomplete) — endpoint PTS
  const urlProfissionais =
    api?.dataset?.urlProfissionais ||
    "/pts/api/profissionais"; // ?q=

  // Legacy (opcional)
  const urlProfissionaisLegacy =
    api?.dataset?.urlProfissionaisLegacy ||
    "/buscar_profissionais_pec";

  // ---------------------------
  // Detecta página
  // ---------------------------
  const formCadastro = $("#formPTS");
  const isCadastro = !!formCadastro;

  const formFiltros = $("#formPtsFiltros");
  const isLista =
    !!$("#tblPtsLista") ||
    !!formFiltros ||
    document.body?.classList?.contains("pts-lista");

  // ===========================================================
  // 1) CADASTRO
  // ===========================================================
  if (isCadastro) {
    // ---------------------------
    // Paciente (campos)
    // ---------------------------
    const nome = $("#nome_paciente");
    const box = $("#sugestoes_paciente");

    const iNascHidden = $("#data_nascimento");
    const iNascVis    = $("#data_nascimento_visivel");
    const iPront      = $("#prontuario");
    const iCns        = $("#cns");
    const iMae        = $("#nome_mae");
    const iSexo       = $("#sexo");
    const iRaca       = $("#raca");
    const iEnd        = $("#endereco");
    const iNum        = $("#numero");
    const iBairro     = $("#bairro");
    const iCep        = $("#cep");
    const iCpf        = $("#cpf");
    const indicadorPaciente = $("#indicadorPaciente");

    const hidPacienteId = $("#paciente_id"); // 🔥 obrigatório para salvar

    const btnLimpar   = $("#btnLimpar");
    const btnImprimir = $("#btnImprimir");

    // ---------------------------
    // Participantes (modo chips)
    // ---------------------------
    const inpPart   = $("#participantesInput");
    const boxPart   = $("#participantesSugestoes");
    const chipsWrap = $("#chipsParticipantes");
    const hiddenIds = $("#participantesIds");

    // Fallback antigo (linhas)
    const lista = $("#lista-participantes");
    const btnAdd = $("#btnAddParticipante");

    // Estado
    let PARTICIPANTES = []; // [{id, nome, cbo, funcao}]
    let lastProfItems = []; // cache do dropdown (pra Enter)

    // ---------------------------
    // PACIENTES
    // ---------------------------
    async function buscarPacientes(q) {
      const url = buildURL(urlSugestoesPaciente, { termo: q });
      const data = await safeJSON(url);
      // teu endpoint geralmente retorna lista direta
      return Array.isArray(data) ? data : (data?.items || []);
    }

    function preencherPaciente(p) {
      if (!p) return;

      // texto
      if (nome) nome.value = p.nome || "";

      // datas
      const { iso, vis } = toISOFromBRorISO(p.nascimento);
      if (iNascHidden) iNascHidden.value = iso;
      if (iNascVis)    iNascVis.value = vis;

      // demais
      if (iPront)  iPront.value = p.prontuario || "";
      if (iCns)    iCns.value = p.cns || "";
      if (iMae)    iMae.value = p.mae || p.nome_mae || "";
      if (iSexo)   iSexo.value = p.sexo || "";
      if (iRaca)   iRaca.value = p.raca || "";
      if (iEnd)    iEnd.value = p.logradouro || p.endereco || "";
      if (iNum)    iNum.value = p.numero || "";
      if (iBairro) iBairro.value = p.bairro || "";
      if (iCep)    iCep.value = p.cep || "";
      if (iCpf)    iCpf.value = p.cpf || "";

      // 🔥 id do paciente (obrigatório)
      if (hidPacienteId) hidPacienteId.value = p.id ? String(p.id) : "";

      // indicador
      if (indicadorPaciente) {
        indicadorPaciente.textContent = p.nome
          ? `Paciente: ${p.nome}`
          : "Nenhum paciente selecionado";
      }

      hideBox(box);
    }

    function renderSugestoesPaciente(items) {
      if (!box) return;
      box.innerHTML = "";

      if (!items.length) {
        box.style.display = "none";
        return;
      }

      items.forEach((p) => {
        const d = document.createElement("div");
        d.className = "sugg-item";
        d.setAttribute("role", "option");
        d.innerHTML = `
          <div class="title">${p.nome || ""}</div>
          <div class="sub">
            ${p.nascimento ? `Nasc.: ${p.nascimento}` : ""}
            ${p.prontuario ? `&nbsp;• Pront.: ${p.prontuario}` : ""}
            ${p.cid ? `&nbsp;• CID: ${p.cid}` : ""}
          </div>
        `;
        d.addEventListener("click", () => preencherPaciente(p));
        box.appendChild(d);
      });

      box.style.display = "block";
    }

    async function onBuscaPaciente() {
      if (!nome || !box) return;
      const q = safeTrim(nome.value);
      hideBox(box);

      // 🔥 paciente: mantém 3+ (igual estava)
      if (q.length < 3) return;

      try {
        const items = await buscarPacientes(q);
        renderSugestoesPaciente(items || []);
      } catch (e) {
        console.error("[PTS] erro buscar pacientes:", e);
      }
    }

    on(nome, "input", debounce(onBuscaPaciente, 240));

    // se o usuário digitar algo manual e apagar, limpa o paciente_id
    on(nome, "change", () => {
      if (!hidPacienteId) return;
      // se não veio de clique (id vazio), não deixa id velho “preso”
      if (!hidPacienteId.value) return;
      // regra simples: se texto não bater com indicador ou algo, zera
      // (evita salvar com paciente errado)
      // aqui a gente só mantém se tiver id
    });

    // fecha dropdown clicando fora
    on(document, "click", (e) => {
      if (!box || !nome) return;
      if (!box.contains(e.target) && e.target !== nome) hideBox(box);
    });

    // ===========================================================
    // PROFISSIONAIS — CHIPS
    // ===========================================================
    async function buscarProfissionais(q) {
      const url = buildURL(urlProfissionais, { q });
      const data = await safeJSON(url);
      const items = data?.items || data?.results || data;
      return Array.isArray(items) ? items : [];
    }

    function syncHiddenParticipantes() {
      if (!hiddenIds) return;
      hiddenIds.value = PARTICIPANTES.map((p) => p.id).join(",");
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
          <span class="chip-name">${p.nome}</span>
          ${p.funcao ? `<span class="chip-sub">${p.funcao}</span>` : ""}
          ${p.cbo ? `<span class="chip-sub">CBO ${p.cbo}</span>` : ""}
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
      const nomeP = safeTrim(item?.nome || "");
      const cboP = safeTrim(item?.cbo || "");
      const funcP = safeTrim(item?.funcao || item?.funcao_sugerida || "");

      if (!id || !nomeP) return;

      const already = PARTICIPANTES.some((x) => x.id === id);
      if (already) return;

      PARTICIPANTES.push({ id, nome: nomeP, cbo: cboP, funcao: funcP });
      renderChips();

      if (inpPart) inpPart.value = "";
      hideBox(boxPart);
      inpPart?.focus();
    }

    function renderSugestoesProfissionais(items) {
      if (!boxPart) return;
      boxPart.innerHTML = "";

      lastProfItems = Array.isArray(items) ? items : [];

      if (!lastProfItems.length) {
        boxPart.style.display = "none";
        return;
      }

      lastProfItems.forEach((p) => {
        const id = Number(p.id);
        const nomeP = safeTrim(p.nome || "");
        const cboP = safeTrim(p.cbo || "");
        const funcaoP = safeTrim(p.funcao || p.funcao_sugerida || "");

        if (!id || !nomeP) return;

        const already = PARTICIPANTES.some((x) => x.id === id);

        const div = document.createElement("div");
        div.className = "sugg-item";
        div.innerHTML = `
          <div class="title">${nomeP}${already ? " (já adicionado)" : ""}</div>
          <div class="sub">
            ${funcaoP ? `Função: ${funcaoP}` : ""}
            ${funcaoP && cboP ? ` &nbsp;•&nbsp; ` : ""}
            ${cboP ? `CBO: ${cboP}` : ""}
          </div>
        `;

        div.addEventListener("click", () => {
          if (already) return;
          addParticipanteFromItem(p);
        });

        boxPart.appendChild(div);
      });

      boxPart.style.display = "block";
    }

    async function onBuscaProfissional() {
      if (!inpPart || !boxPart) return;

      const q = safeTrim(inpPart.value);
      hideBox(boxPart);

      // 🔥 PROFISSIONAIS: somente a partir do 3º caractere
      if (q.length < 3) return;

      try {
        const items = await buscarProfissionais(q);
        renderSugestoesProfissionais(items);
      } catch (e) {
        console.warn("[PTS] erro buscar profissionais:", e);
      }
    }

    on(inpPart, "input", debounce(onBuscaProfissional, 220));

    // Enter adiciona o primeiro resultado
    on(inpPart, "keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (lastProfItems && lastProfItems.length) {
          addParticipanteFromItem(lastProfItems[0]);
        }
      }
      if (e.key === "Escape") {
        hideBox(boxPart);
      }
    });

    on(document, "click", (e) => {
      if (!boxPart || !inpPart) return;
      if (!boxPart.contains(e.target) && e.target !== inpPart) hideBox(boxPart);
    });

    // inicia chips
    renderChips();

    // ===========================================================
    // LEGACY (opcional) — linhas
    // ===========================================================
    let PROFISSIONAIS_LEGACY = [];

    async function carregarProfissionaisLegacy() {
      try {
        const data = await safeJSON(urlProfissionaisLegacy);
        PROFISSIONAIS_LEGACY = Array.isArray(data) ? data : [];
      } catch (e) {
        PROFISSIONAIS_LEGACY = [];
      }
    }

    function mkSelect(opts, { name, placeholder }) {
      const sel = document.createElement("select");
      sel.name = name;
      sel.required = true;
      sel.className = "form-select";
      sel.innerHTML = `<option value="">${placeholder || "Selecione"}</option>`;
      opts.forEach((o) => {
        const op = document.createElement("option");
        op.value = o.value;
        op.textContent = o.label;
        sel.appendChild(op);
      });
      return sel;
    }

    function addParticipanteRowLegacy(prefill) {
      if (!lista) return;

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
      lista.appendChild(row);
    }

    on(btnAdd, "click", async () => {
      if (!lista) return;
      if (!PROFISSIONAIS_LEGACY.length) {
        alert("Lista de profissionais ainda não carregada. Tentando novamente...");
        await carregarProfissionaisLegacy();
      }
      addParticipanteRowLegacy();
    });

    // ===========================================================
    // UTILIDADES
    // ===========================================================
    on(btnLimpar, "click", () => {
      formCadastro.reset();

      // limpa paciente_id
      if (hidPacienteId) hidPacienteId.value = "";

      if (indicadorPaciente) {
        indicadorPaciente.textContent = "Nenhum paciente selecionado";
      }

      if (lista) lista.innerHTML = "";

      // limpa chips
      PARTICIPANTES = [];
      renderChips();

      // limpa dropdowns
      hideBox(box);
      hideBox(boxPart);

      nome?.focus();
    });

    on(btnImprimir, "click", () => window.print());

    // 🔥 validação do paciente_id (evita “preciso do ID”)
    on(formCadastro, "submit", (e) => {
      const pid = safeTrim(hidPacienteId?.value);
      if (!pid) {
        e.preventDefault();
        alert("Selecione um paciente na lista (preciso do ID).");
        nome?.focus();
        return;
      }

      // valida campos obrigatórios do seu form
      const obrig = ["nome_paciente", "localizacao_territorial", "diagnostico_funcional"];
      const falta = obrig.filter(
        (n) => !formCadastro.elements[n] || !safeTrim(formCadastro.elements[n].value)
      );
      if (falta.length) {
        e.preventDefault();
        alert("Preencha os campos obrigatórios do PTS.");
        formCadastro.elements[falta[0]]?.focus();
        return;
      }

      // garante sync final
      syncHiddenParticipantes();
    });

    // Init
    (async function initCadastro() {
      // legacy opcional
      if (btnAdd && lista) {
        await carregarProfissionaisLegacy();
      }
      renderChips();
    })();
  }

  // ===========================================================
  // 5) LISTA / VISUALIZAR: UX
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
  }
})();
