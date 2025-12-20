// cadastro/static/js/cadastro.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("formCadastro");

  const nascimentoInput = document.getElementById("nascimento");
  const idadeInput = document.getElementById("idade");
  const admissaoInput = document.getElementById("admissao");
  const prontuarioInput = document.getElementById("prontuario");
  const modInput = document.getElementById("mod");

  // =========================
  // Helpers base
  // =========================
  const $digits = (s) => String(s || "").replace(/\D+/g, "");
  const $trim = (s) => (s == null ? "" : String(s).trim());

  function hojeISO() {
    return new Date().toISOString().split("T")[0]; // YYYY-MM-DD
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

  // =========================
  // Prontuário (SEM SGD)
  // =========================
  function sanitizeProntuario(v) {
    // remove prefixos SGD/SGD-
    const s = $trim(v);
    if (!s) return "";
    const up = s.toUpperCase();
    if (up.startsWith("SGD-")) return $trim(s.slice(4));
    if (up.startsWith("SGD")) return $trim(s.slice(3));
    return s;
  }

  function gerarProntuario() {
    // exemplo: AA + 4 dígitos (6 chars), tudo numérico (mais fácil pra recepção)
    // 2025 -> "25" + 4 dígitos = "251234"
    const ano = String(new Date().getFullYear()).slice(-2);
    const numero = Math.floor(1000 + Math.random() * 9000); // 1000..9999
    return `${ano}${numero}`;
  }

  // =========================
  // Modalidade (MOD) padrão novo
  // =========================
  const ALLOWED_MODS = new Set(["FIS", "INT", "AUD", "EQUO", "MED", "VISU", "EXAM", "SEM MOD"]);

  // Aceita entradas antigas e converte pro novo
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

  function normalizeMod(v) {
    const raw = $trim(v);
    const up = raw.toUpperCase();
    const mapped = MOD_MAP[up];
    if (mapped && ALLOWED_MODS.has(mapped)) return mapped;
    if (ALLOWED_MODS.has(up)) return up;
    return "SEM MOD";
  }

  // =========================
  // Normalização payload (espelha backend)
  // =========================
  const UPPER_FIELDS = new Set([
    "nome",
    "status",
    "cid",
    "cid2",
    "raca",
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
    // OBS: "admissao" NÃO entra (é data)
    // OBS: "mod" vai por normalizeMod()
    // OBS: "prontuario" vai por sanitizeProntuario()
  ]);

  function toUpper(x) {
    return x == null ? "" : String(x).trim().toUpperCase();
  }

  function normalizePayload(obj) {
    const out = {};

    for (const [k, v] of Object.entries(obj)) {
      if (UPPER_FIELDS.has(k)) {
        out[k] = toUpper(v);
      } else if (k === "email") {
        out[k] = $trim(v).toLowerCase();
      } else if (k === "sexo") {
        out[k] = $trim(v).toUpperCase().slice(0, 1); // M/F
      } else if (k === "mod") {
        out[k] = normalizeMod(v);
      } else if (k === "prontuario") {
        out[k] = sanitizeProntuario(v);
      } else if (k === "cpf" || k.endsWith("_cpf") || k.startsWith("cpf_")) {
        // opcional: mantém como digitado (o backend pode cuidar), mas ajuda a padronizar se quiser:
        out[k] = $trim(v);
      } else {
        out[k] = typeof v === "string" ? v.trim() : v;
      }
    }

    // admissão: se vier vazia, manda vazia (backend coloca hoje), MAS aqui podemos reforçar:
    if (!out.admissao || !$trim(out.admissao)) {
      out.admissao = ""; // deixa o backend decidir (ou seta hojeISO() se preferir)
    }

    // garantia final MOD
    out.mod = normalizeMod(out.mod);

    return out;
  }

  // =========================
  // Init (sem sobrescrever)
  // =========================
  if (prontuarioInput) {
    // se já existe algo (ex: edição futura), respeita; senão gera
    const atual = sanitizeProntuario(prontuarioInput.value);
    prontuarioInput.value = atual || gerarProntuario();
  }

  // admissão: só preenche se estiver vazio (pra não brigar com Jinja value="{{ admissao_sugestao }}")
  if (admissaoInput) {
    if (!$trim(admissaoInput.value)) admissaoInput.value = hojeISO();
    // é sugestão: NÃO readonly
    // (se teu HTML ainda tiver readonly, remove no template)
  }

  // força o select mod pro padrão novo (se vier qualquer coisa esquisita)
  if (modInput) {
    modInput.value = normalizeMod(modInput.value);
  }

  // =========================
  // Listeners
  // =========================
  if (nascimentoInput && idadeInput) {
    const syncIdade = () => {
      idadeInput.value = calcularIdade(nascimentoInput.value);
    };
    nascimentoInput.addEventListener("change", syncIdade);
    nascimentoInput.addEventListener("blur", syncIdade);
    // se já veio preenchido
    if ($trim(nascimentoInput.value)) syncIdade();
  }

  if (prontuarioInput) {
    // mesmo sendo readonly, se algum dia virar editável, já fica blindado
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

  // =========================
  // Submit (fetch JSON)
  // =========================
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const formData = new FormData(form);
      const dados = {};
      for (const [key, value] of formData.entries()) {
        dados[key] = value;
      }

      // garante idade se nascimento veio
      if ($trim(dados.nascimento) && !$trim(dados.idade)) {
        dados.idade = calcularIdade(dados.nascimento);
      }

      // garante prontuário sem SGD e não vazio
      dados.prontuario = sanitizeProntuario(dados.prontuario);
      if (!dados.prontuario) {
        dados.prontuario = gerarProntuario();
      }

      // mod padronizado
      dados.mod = normalizeMod(dados.mod);

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
          if (!response.ok) throw new Error(data.mensagem || "Falha ao salvar.");
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

            // regen autos
            if (prontuarioInput) prontuarioInput.value = gerarProntuario();
            if (admissaoInput && !$trim(admissaoInput.value)) admissaoInput.value = hojeISO();
            if (idadeInput) idadeInput.value = "";
            if (modInput) modInput.value = "SEM MOD";
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
