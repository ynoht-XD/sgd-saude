document.addEventListener("DOMContentLoaded", () => {
  "use strict";

  const form = document.getElementById("formCadastro");

  const nascimentoInput = document.getElementById("nascimento");
  const idadeInput = document.getElementById("idade");
  const admissaoInput = document.getElementById("admissao");
  const prontuarioInput = document.getElementById("prontuario");
  const modInput = document.getElementById("mod");

  const cepInput = document.getElementById("cep");
  const municipioInput = document.getElementById("municipio");
  const codigoIbgeInput = document.getElementById("codigo_ibge");
  const cepStatus = document.getElementById("cep-status");
  const enderecoLockedFields = Array.from(
    document.querySelectorAll("[data-cep-lock='true']")
  );

  const laudoBuscaInput = document.getElementById("laudo-cid-busca");
  const laudoSelecionadoInput = document.getElementById("laudo-cid-selecionado");
  const laudoSugestoes = document.getElementById("laudo-cid-sugestoes");
  const btnAdicionarLaudo = document.getElementById("btnAdicionarLaudo");
  const laudosLista = document.getElementById("laudosLista");
  const laudosJsonInput = document.getElementById("laudos_json");

  let laudoSelecionado = null;
  let laudos = [];
  let debounceTimer = null;

  const $digits = (s) => String(s || "").replace(/\D+/g, "");
  const $trim = (s) => (s == null ? "" : String(s).trim());

  function hojeISO() {
    return new Date().toISOString().split("T")[0];
  }

  function calcularIdade(dataNascStr) {
    const s = $trim(dataNascStr);
    if (!s) return "";

    const hoje = new Date();
    const nasc = new Date(s);
    if (isNaN(nasc.getTime())) return "";

    let idade = hoje.getFullYear() - nasc.getFullYear();
    const m = hoje.getMonth() - nasc.getMonth();
    if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) idade--;

    return String(idade);
  }

  function sanitizeProntuario(v) {
    const s = $trim(v);
    if (!s) return "";

    const up = s.toUpperCase();
    if (up.startsWith("SGD-")) return $trim(s.slice(4));
    if (up.startsWith("SGD")) return $trim(s.slice(3));
    return s;
  }

  function gerarProntuario() {
    const ano = String(new Date().getFullYear()).slice(-2);
    const numero = Math.floor(1000 + Math.random() * 9000);
    return `${ano}${numero}`;
  }

  const ALLOWED_MODS = new Set([
    "FIS", "INT", "AUD", "EQUO", "MED", "VISU", "EXAM", "SEM MOD"
  ]);

  const MOD_MAP = {
    "FIS": "FIS",
    "FISIOTERAPIA": "FIS",
    "FÍSICO": "FIS",
    "FISICO": "FIS",

    "INT": "INT",
    "INTELECTUAL": "INT",

    "AUD": "AUD",
    "AUDITIVO": "AUD",
    "AUDITIVA": "AUD",

    "EQUO": "EQUO",
    "EQUOTERAPIA": "EQUO",

    "MED": "MED",
    "MEDICO": "MED",
    "MÉDICO": "MED",

    "VISU": "VISU",
    "VISUAL": "VISU",

    "EXAM": "EXAM",
    "EXAME": "EXAM",
    "EXAMES": "EXAM",

    "SEM MOD": "SEM MOD",
    "SEM MODALIDADE": "SEM MOD",
    "SEM": "SEM MOD",
    "": "SEM MOD",
  };

  const UPPER_FIELDS = new Set([
    "nome",
    "status",
    "raca",
    "religiao",
    "logradouro",
    "codigo_logradouro",
    "complemento",
    "bairro",
    "municipio",
    "orgao_rg",
    "orgao_rg_responsavel",
    "estado_civil",
    "mae",
    "pai",
    "responsavel",
  ]);

  function toUpper(x) {
    return x == null ? "" : String(x).trim().toUpperCase();
  }

  function normalizeMod(v) {
    const raw = $trim(v);
    const up = raw.toUpperCase();
    const mapped = MOD_MAP[up];
    if (mapped && ALLOWED_MODS.has(mapped)) return mapped;
    if (ALLOWED_MODS.has(up)) return up;
    return "SEM MOD";
  }

  function normalizePayload(obj) {
    const out = {};

    for (const [k, v] of Object.entries(obj)) {
      if (UPPER_FIELDS.has(k)) {
        out[k] = toUpper(v);
      } else if (k === "email") {
        out[k] = $trim(v).toLowerCase();
      } else if (k === "sexo") {
        out[k] = $trim(v).toUpperCase().slice(0, 1);
      } else if (k === "mod") {
        out[k] = normalizeMod(v);
      } else if (k === "prontuario") {
        out[k] = sanitizeProntuario(v);
      } else if (k === "cep") {
        out[k] = $digits(v).slice(0, 8);
      } else if (k === "codigo_ibge") {
        out[k] = $digits(v);
      } else {
        out[k] = typeof v === "string" ? v.trim() : v;
      }
    }

    if (!out.admissao || !$trim(out.admissao)) out.admissao = "";
    out.mod = normalizeMod(out.mod);

    return out;
  }

  function setCepStatus(texto, tipo = "neutro") {
    if (!cepStatus) return;
    cepStatus.textContent = texto;
    cepStatus.className = `cep-status cep-status--${tipo}`;
  }

  function lockEndereco(lock = true) {
    enderecoLockedFields.forEach((field) => {
      if (!field) return;
      field.disabled = lock;

      if (field.id === "municipio" || field.id === "codigo_ibge") {
        field.readOnly = true;
      }
    });
  }

  function limparEnderecoDependente() {
    if (municipioInput) municipioInput.value = "";
    if (codigoIbgeInput) codigoIbgeInput.value = "";

    enderecoLockedFields.forEach((field) => {
      if (!field) return;
      if (field.id === "municipio" || field.id === "codigo_ibge") return;
      field.value = "";
    });
  }

  function formatCEP(value) {
    const digits = $digits(value).slice(0, 8);
    if (digits.length <= 5) return digits;
    return `${digits.slice(0, 5)}-${digits.slice(5)}`;
  }

  async function buscarCep(cep) {
    const cepDigits = $digits(cep).slice(0, 8);

    if (cepDigits.length < 8) {
      lockEndereco(true);
      limparEnderecoDependente();
      setCepStatus("Informe o CEP completo para liberar os campos de endereço.", "neutro");
      return;
    }

    setCepStatus("Buscando CEP na base local...", "carregando");

    try {
      const response = await fetch(`/api/cep/buscar?cep=${encodeURIComponent(cepDigits)}`);
      const data = await response.json();

      if (!response.ok || !data.ok) {
        lockEndereco(true);
        limparEnderecoDependente();
        setCepStatus(data.mensagem || "CEP não encontrado.", "erro");
        return;
      }

      if (municipioInput) municipioInput.value = data.item.municipio || "";
      if (codigoIbgeInput) codigoIbgeInput.value = data.item.ibge || "";

      lockEndereco(false);
      setCepStatus("CEP localizado. Campos de endereço liberados.", "sucesso");
    } catch (error) {
      console.error("Erro ao buscar CEP:", error);
      lockEndereco(true);
      limparEnderecoDependente();
      setCepStatus("Erro ao consultar o CEP.", "erro");
    }
  }

  function syncLaudosJson() {
    if (!laudosJsonInput) return;
    laudosJsonInput.value = JSON.stringify(laudos);
  }

  function renderLaudos() {
    if (!laudosLista) return;

    if (!laudos.length) {
      laudosLista.innerHTML = `<div class="laudos-vazio">Nenhum CID adicionado ainda.</div>`;
      syncLaudosJson();
      return;
    }

    laudosLista.innerHTML = laudos.map((item, index) => `
      <div class="laudo-chip" data-index="${index}">
        <div class="laudo-chip-texto">
          <strong>${item.codigo || ""}</strong>
          <span>${item.descricao || ""}</span>
        </div>
        <button
          type="button"
          class="laudo-chip-remove"
          data-remove-index="${index}"
          aria-label="Remover CID"
        >
          ×
        </button>
      </div>
    `).join("");

    syncLaudosJson();
  }

  function esconderSugestoesLaudo() {
    if (!laudoSugestoes) return;
    laudoSugestoes.innerHTML = "";
    laudoSugestoes.hidden = true;
  }

  function limparInputsLaudo() {
    laudoSelecionado = null;
    if (laudoSelecionadoInput) laudoSelecionadoInput.value = "";
    if (laudoBuscaInput) laudoBuscaInput.value = "";
    esconderSugestoesLaudo();
  }

  function preencherLaudoSelecionado(codigo, descricao) {
    laudoSelecionado = {
      codigo: $trim(codigo),
      descricao: $trim(descricao),
    };

    const texto = [laudoSelecionado.codigo, laudoSelecionado.descricao]
      .filter(Boolean)
      .join(" - ");

    if (laudoSelecionadoInput) {
      laudoSelecionadoInput.value = texto;
    }

    if (laudoBuscaInput) {
      laudoBuscaInput.value = texto;
    }

    esconderSugestoesLaudo();
  }

  function mostrarSugestoesLaudo(items) {
    if (!laudoSugestoes) return;

    if (!items.length) {
      laudoSugestoes.innerHTML = `<div class="autocomplete-empty">Nenhum CID encontrado.</div>`;
      laudoSugestoes.hidden = false;
      return;
    }

    laudoSugestoes.innerHTML = items.map((item) => `
      <button
        type="button"
        class="autocomplete-item"
        data-codigo="${String(item.codigo || "").replace(/"/g, "&quot;")}"
        data-descricao="${String(item.descricao || "").replace(/"/g, "&quot;")}"
      >
        <strong>${item.codigo || ""}</strong>
        <span>${item.descricao || ""}</span>
      </button>
    `).join("");

    laudoSugestoes.hidden = false;
  }

  async function buscarSugestoesCid(q) {
    const termo = $trim(q);

    if (termo.length < 2) {
      esconderSugestoesLaudo();
      return;
    }

    try {
      const response = await fetch(`/api/cids/buscar?q=${encodeURIComponent(termo)}`);
      const data = await response.json();

      if (!response.ok || !data.ok) {
        mostrarSugestoesLaudo([]);
        return;
      }

      mostrarSugestoesLaudo(data.items || []);
    } catch (error) {
      console.error("Erro ao buscar CIDs:", error);
      mostrarSugestoesLaudo([]);
    }
  }

  function adicionarLaudoSelecionado() {
    if (!laudoSelecionado) {
      alert("Selecione um CID na busca antes de adicionar.");
      return;
    }

    const codigo = $trim(laudoSelecionado.codigo).toUpperCase();
    const descricao = $trim(laudoSelecionado.descricao).toUpperCase();

    const jaExiste = laudos.some((item) =>
      $trim(item.codigo).toUpperCase() === codigo &&
      $trim(item.descricao).toUpperCase() === descricao
    );

    if (jaExiste) {
      alert("Esse CID já foi adicionado.");
      return;
    }

    laudos.push({ codigo, descricao });
    renderLaudos();
    limparInputsLaudo();

    if (laudoBuscaInput) {
      laudoBuscaInput.focus();
    }
  }

  if (prontuarioInput) {
    const atual = sanitizeProntuario(prontuarioInput.value);
    prontuarioInput.value = atual || gerarProntuario();
  }

  if (admissaoInput && !$trim(admissaoInput.value)) {
    admissaoInput.value = hojeISO();
  }

  if (modInput) {
    modInput.value = normalizeMod(modInput.value);
  }

  lockEndereco(true);
  setCepStatus("Informe o CEP para liberar os campos de endereço.", "neutro");
  renderLaudos();

  if (nascimentoInput && idadeInput) {
    const syncIdade = () => {
      idadeInput.value = calcularIdade(nascimentoInput.value);
    };

    nascimentoInput.addEventListener("change", syncIdade);
    nascimentoInput.addEventListener("blur", syncIdade);

    if ($trim(nascimentoInput.value)) syncIdade();
  }

  if (prontuarioInput) {
    prontuarioInput.addEventListener("blur", () => {
      prontuarioInput.value = sanitizeProntuario(prontuarioInput.value);
    });
  }

  if (modInput) {
    modInput.addEventListener("change", () => {
      modInput.value = normalizeMod(modInput.value);
    });

    modInput.addEventListener("blur", () => {
      modInput.value = normalizeMod(modInput.value);
    });
  }

  if (cepInput) {
    cepInput.addEventListener("input", () => {
      cepInput.value = formatCEP(cepInput.value);
      const digits = $digits(cepInput.value);

      if (digits.length < 8) {
        lockEndereco(true);
        limparEnderecoDependente();
        setCepStatus("Informe o CEP completo para liberar os campos de endereço.", "neutro");
      }
    });

    cepInput.addEventListener("blur", () => {
      buscarCep(cepInput.value);
    });
  }

  if (laudoBuscaInput) {
    laudoBuscaInput.addEventListener("input", () => {
      const termo = laudoBuscaInput.value;

      laudoSelecionado = null;
      if (laudoSelecionadoInput) laudoSelecionadoInput.value = "";

      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        buscarSugestoesCid(termo);
      }, 250);
    });

    laudoBuscaInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();

        if (laudoSelecionado) {
          adicionarLaudoSelecionado();
          return;
        }

        const primeiroItem = laudoSugestoes?.querySelector(".autocomplete-item");
        if (primeiroItem) {
          preencherLaudoSelecionado(
            primeiroItem.dataset.codigo || "",
            primeiroItem.dataset.descricao || ""
          );
          adicionarLaudoSelecionado();
        }
      }
    });

    laudoBuscaInput.addEventListener("blur", () => {
      setTimeout(() => {
        esconderSugestoesLaudo();
      }, 220);
    });
  }

  if (laudoSugestoes) {
    laudoSugestoes.addEventListener("mousedown", (e) => {
      const btn = e.target.closest(".autocomplete-item");
      if (!btn) return;

      e.preventDefault();

      preencherLaudoSelecionado(
        btn.dataset.codigo || "",
        btn.dataset.descricao || ""
      );
    });
  }

  if (btnAdicionarLaudo) {
    btnAdicionarLaudo.addEventListener("click", () => {
      adicionarLaudoSelecionado();
    });
  }

  if (laudosLista) {
    laudosLista.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-remove-index]");
      if (!btn) return;

      const index = Number(btn.dataset.removeIndex);
      if (Number.isNaN(index)) return;

      laudos.splice(index, 1);
      renderLaudos();
    });
  }

  document.addEventListener("click", (e) => {
    const clicouNaBusca = e.target.closest(".laudos-busca-wrap");
    const clicouNaLista = e.target.closest("#laudo-cid-sugestoes");

    if (!clicouNaBusca && !clicouNaLista) {
      esconderSugestoesLaudo();
    }
  });

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const formData = new FormData(form);
      const dados = {};

      for (const [key, value] of formData.entries()) {
        dados[key] = value;
      }

      if ($trim(dados.nascimento) && !$trim(dados.idade)) {
        dados.idade = calcularIdade(dados.nascimento);
      }

      dados.prontuario = sanitizeProntuario(dados.prontuario);
      if (!dados.prontuario) {
        dados.prontuario = gerarProntuario();
      }

      dados.mod = normalizeMod(dados.mod);
      dados.cep = $digits(dados.cep).slice(0, 8);
      dados.codigo_ibge = $digits(dados.codigo_ibge);
      dados.laudos_json = JSON.stringify(laudos);

      const payload = normalizePayload(dados);

      fetch("/cadastro", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(async (response) => {
          let data;
          try {
            data = await response.json();
          } catch {
            data = { status: "erro", mensagem: "Resposta inválida do servidor." };
          }

          if (!response.ok) {
            throw new Error(data.mensagem || "Falha ao salvar.");
          }

          return data;
        })
        .then((data) => {
          if (data.status === "sucesso") {
            if (data.redirect) {
              window.location = data.redirect;
              return;
            }

            alert("✅ Cadastro realizado com sucesso!");
            form.reset();

            laudos = [];
            renderLaudos();
            laudoSelecionado = null;
            esconderSugestoesLaudo();

            if (prontuarioInput) prontuarioInput.value = gerarProntuario();
            if (admissaoInput) admissaoInput.value = hojeISO();
            if (idadeInput) idadeInput.value = "";
            if (modInput) modInput.value = "SEM MOD";

            lockEndereco(true);
            limparEnderecoDependente();
            setCepStatus("Informe o CEP para liberar os campos de endereço.", "neutro");
          } else {
            alert("❌ Erro ao cadastrar: " + (data.mensagem || "Desconhecido"));
          }
        })
        .catch((error) => {
          console.error("Erro:", error);
          alert("❌ Erro: " + error.message);
        });
    });
  }
});