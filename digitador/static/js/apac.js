// sgd/digitador/static/js/apac.js
(() => {
  // ========== Helpers ==========
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, ev, fn, opts) => el && el.addEventListener(ev, fn, opts);
  const debounce = (fn, ms = 250) => {
    let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  };

  const onlyDigits = (s = "") => s.replace(/\D+/g, "");
  const pad2 = (n) => String(n).padStart(2, "0");

  const parseDateLoose = (val) => {
    if (!val) return null;
    // tenta ISO yyyy-mm-dd
    const iso = new Date(val);
    if (!Number.isNaN(iso.getTime())) return iso;
    // tenta dd/mm/yyyy
    const m = /^(\d{2})[\/\-](\d{2})[\/\-](\d{4})$/.exec(val);
    if (m) {
      const d = new Date(`${m[3]}-${m[2]}-${m[1]}`);
      if (!Number.isNaN(d.getTime())) return d;
    }
    return null;
  };

  const formatDDMMYYYY = (d) => `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
  const formatYYYYMMDD = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

  // adiciona meses preservando dia quando possível
  const addMonths = (date, months) => {
    const d = new Date(date);
    const day = d.getDate();
    d.setMonth(d.getMonth() + months);
    // se estourar pro mês seguinte, ajusta pro último dia válido
    if (d.getDate() < day) d.setDate(0);
    return d;
  };

  // ========== Elements ==========
  const elApi = $("#apacApi");
  const urlSugestoes =
    elApi?.dataset?.urlSugestoes ||
    "/api/consulta_pacientes"; // fallback (caso tenha essa rota)

  const elCompetenciaData = $("#competencia_data");
  const elCompetencia = $("#competencia");
  const elDataInicial = $("#data_inicial");
  const elDataFinal = $("#data_final");
  const elDataSolicitacao = $("#data_solicitacao");
  const elDataAlta = $("#data_alta");
  const elDataAutorizacao = $("#data_autorizacao");

  const elNome = $("#nome_paciente");
  const elSugg = $("#sugestoes_paciente");

  const elNascVisivel = $("#data_nascimento_visivel");
  const elNasc = $("#data_nascimento");
  const elProntuario = $("#prontuario");
  const elCNS = $("#cns");
  const elMae = $("#nome_mae");
  const elSexo = $("#sexo");
  const elRaca = $("#raca");
  const elCodLog = $("#cod_logradouro");
  const elEndereco = $("#endereco");
  const elNumero = $("#numero");
  const elBairro = $("#bairro");
  const elCEP = $("#cep");

  const elBtnLimpar = $("#btnLimpar");
  const elBtnImprimir = $("#btnImprimir");
  const elIndicadorPaciente = $("#indicadorPaciente");
  const form = $("#form-apac");

  // ========== Regras de datas ==========
  on(elCompetenciaData, "change", () => {
    const d = parseDateLoose(elCompetenciaData.value);
    if (d && elCompetencia) {
      elCompetencia.value = `${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
    }
  });

  on(elDataInicial, "change", () => {
    const di = parseDateLoose(elDataInicial.value);
    if (!di) return;
    const df = addMonths(di, 3);
    if (elDataFinal) elDataFinal.value = formatYYYYMMDD(df);
    if (elDataSolicitacao) elDataSolicitacao.value = formatYYYYMMDD(di);
  });

  on(elDataAlta, "change", () => {
    if (elDataAutorizacao) elDataAutorizacao.value = elDataAlta.value || "";
  });

  // ========== Autocomplete Paciente ==========
  let suggIndex = -1; // item focado
  const closeSugg = () => { elSugg?.classList.remove("open"); elSugg.innerHTML = ""; suggIndex = -1; };
  const openSugg = () => { elSugg?.classList.add("open"); };

  const renderSugestoes = (lista) => {
    if (!elSugg) return;
    elSugg.innerHTML = "";
    if (!lista?.length) { closeSugg(); return; }

    lista.forEach((p, i) => {
      const nasc = p.nascimento || p.data_nascimento || "";
      const item = document.createElement("div");
      item.className = "sugg-item";
      item.setAttribute("role", "option");
      item.setAttribute("data-index", String(i));
      item.innerHTML = `<strong>${p.nome}</strong> <span class="muted"> ${nasc ? `(${nasc})` : ""}</span>`;
      on(item, "mousedown", (e) => { e.preventDefault(); selectPaciente(p); }); // mousedown evita blur
      elSugg.appendChild(item);
    });
    openSugg();
  };

  const selectPaciente = (p) => {
    if (elNome) elNome.value = p.nome || "";

    const nasc = p.nascimento || p.data_nascimento || "";
    const d = parseDateLoose(nasc);
    if (d) {
      if (elNascVisivel) elNascVisivel.value = formatDDMMYYYY(d);
      if (elNasc) elNasc.value = formatYYYYMMDD(d);
    } else {
      if (elNascVisivel) elNascVisivel.value = "";
      if (elNasc) elNasc.value = "";
    }

    if (elProntuario) elProntuario.value = p.prontuario || "";
    if (elCNS) elCNS.value = p.cns || p.CNS || "";
    if (elMae) elMae.value = p.mae || p.nome_mae || "";
    if (elSexo) elSexo.value = p.sexo || "";
    if (elRaca) elRaca.value = p.raca || elRaca?.value || ""; // mantém padrão se existir
    if (elCodLog) elCodLog.value = p.cod_logradouro || elCodLog?.value || "081";
    if (elEndereco) elEndereco.value = p.logradouro || p.endereco || "";
    if (elNumero) elNumero.value = p.numero || "";
    if (elBairro) elBairro.value = p.bairro || "";
    if (elCEP) elCEP.value = p.cep || "";

    if (elIndicadorPaciente) elIndicadorPaciente.textContent = p.nome ? `Paciente: ${p.nome}` : "Nenhum paciente selecionado";
    closeSugg();
  };

  const fetchSugestoes = async (q) => {
    try {
      const url = new URL(urlSugestoes, window.location.origin);
      // nossos endpoints usam 'termo' (atendimentos.sugestoes_pacientes) ou 'nome' (fallback)
      url.searchParams.set("termo", q);
      // para compatibilidade com outra rota antiga:
      url.searchParams.set("nome", q);

      const res = await fetch(url.toString(), { headers: { "Accept": "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // normaliza campos pra render
      return (data || []).map(r => ({
        id: r.id,
        nome: r.nome,
        prontuario: r.prontuario,
        nascimento: r.nascimento || r.data_nascimento || "",
        cns: r.cns || "",
        mae: r.mae || r.nome_mae || "",
        sexo: r.sexo || "",
        raca: r.raca || "",
        logradouro: r.logradouro || r.endereco || "",
        numero: r.numero || "",
        bairro: r.bairro || "",
        cep: r.cep || ""
      }));
    } catch (err) {
      console.error("Erro ao buscar sugestões:", err);
      return [];
    }
  };

  on(elNome, "input", debounce(async (e) => {
    const q = (e.target.value || "").trim();
    if (q.length < 3) { closeSugg(); return; }
    const lista = await fetchSugestoes(q);
    renderSugestoes(lista.slice(0, 12));
  }, 250));

  on(elNome, "keydown", (e) => {
    if (!elSugg?.classList.contains("open")) return;
    const items = $$(".sugg-item", elSugg);
    if (!items.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      suggIndex = (suggIndex + 1) % items.length;
      highlight(items, suggIndex);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      suggIndex = (suggIndex - 1 + items.length) % items.length;
      highlight(items, suggIndex);
    } else if (e.key === "Enter") {
      if (suggIndex >= 0) {
        e.preventDefault();
        items[suggIndex].dispatchEvent(new Event("mousedown"));
      }
    } else if (e.key === "Escape") {
      closeSugg();
    }
  });

  const highlight = (items, idx) => {
    items.forEach((it, i) => it.setAttribute("aria-selected", i === idx ? "true" : "false"));
    const el = items[idx];
    if (el) {
      const box = elSugg.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      if (r.bottom > box.bottom) el.scrollIntoView(false);
      if (r.top < box.top) el.scrollIntoView();
    }
  };

  // fecha sugestões ao clicar fora
  on(document, "click", (e) => {
    if (!elSugg) return;
    if (e.target === elNome || elSugg.contains(e.target)) return;
    closeSugg();
  });

  // ========== Ações topo ==========
  on(elBtnLimpar, "click", () => {
    form?.reset();
    if (elNascVisivel) elNascVisivel.value = "";
    if (elIndicadorPaciente) elIndicadorPaciente.textContent = "Nenhum paciente selecionado";
    closeSugg();
  });

  on(elBtnImprimir, "click", () => window.print());

  // ========== Submit (preview – validações leves) ==========
  on(form, "submit", (e) => {
    // HTML5 required já cobre boa parte.
    // Aqui só garantimos que data_final/solicitação/autorização estejam coerentes se inicial/alta vieram.
    const di = parseDateLoose(elDataInicial?.value);
    if (di && elDataFinal && !elDataFinal.value) {
      elDataFinal.value = formatYYYYMMDD(addMonths(di, 3));
    }
    if (di && elDataSolicitacao && !elDataSolicitacao.value) {
      elDataSolicitacao.value = formatYYYYMMDD(di);
    }
    const da = parseDateLoose(elDataAlta?.value);
    if (da && elDataAutorizacao && !elDataAutorizacao.value) {
      elDataAutorizacao.value = formatYYYYMMDD(da);
    }
    // segue o submit normal (POST futuro)
  });

  // ========== Boot ==========
  // se já existir valor em competência_data ao abrir (voltar de post), calcule:
  if (elCompetenciaData?.value) elCompetenciaData.dispatchEvent(new Event("change"));
  if (elDataInicial?.value) elDataInicial.dispatchEvent(new Event("change"));
})();
