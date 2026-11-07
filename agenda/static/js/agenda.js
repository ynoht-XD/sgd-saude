// agenda/static/js/agenda.js
(() => {
  // ================== helpers ==================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content || "";

  const ENDPOINT_SAVE         = meta("agenda-save-endpoint");
  const ENDPOINT_SUGGEST      = meta("pacientes-suggest-endpoint");        // antigo (so nome) - usado so como reserva
  const ENDPOINT_PAC_BUSCA    = meta("pacientes-busca-endpoint") || "/agenda/api/pacientes"; // novo: devolve ID
  const ENDPOINT_PROS         = meta("profissionais-endpoint");
  const ENDPOINT_AGREG        = meta("agregados-endpoint");
  const ENDPOINT_EXPORT       = meta("agregados-export-endpoint");

  const ENDPOINT_AGEND_BASE   = "/agenda/api/agendamentos"; // PUT/DELETE por ID
  const ENDPOINT_DELETE_GROUP = "/agenda/api/agregados";    // DELETE por grupo (dow+hora+prof+pac)

  // CPF do profissional logado vindo do template
  const CURRENT_PROF_CPF = meta("current-prof-cpf") || "";
  const onlyDigits = (v) => (v || "").replace(/\D/g, "");

  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  const MODALIDADE_LABEL = { combo: "Combo", plano: "Plano" };
  const modalidadeLabel = (m) => MODALIDADE_LABEL[String(m || "").toLowerCase()] || "";

  const chaveNome = (n) => String(n || "")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/\s+/g, " ").trim();

  const dataBR = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
  };

  function whatsappHref(numero) {
    const digits = onlyDigits(numero);

    if (!digits) return "";

    // Se já vier com 55, mantém. Se vier só DDD+número, adiciona 55.
    const finalNumber = digits.startsWith("55") ? digits : `55${digits}`;

    return `https://wa.me/${finalNumber}`;
  }

  function telefonePacienteHTML(numero) {
    const digits = onlyDigits(numero);

    if (!digits) {
      return `<span class="ag-card-phone empty">Sem telefone</span>`;
    }

    return `
      <a 
        class="ag-card-phone"
        href="${whatsappHref(numero)}"
        target="_blank"
        rel="noopener"
        title="Abrir WhatsApp"
      >
        <span>📱</span>
        <span>${numero}</span>
      </a>
    `;
  }

  console.debug("[agenda] META current-prof-cpf:", CURRENT_PROF_CPF);

  const debounce = (fn, ms = 250) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  };

  const DIA_LABEL = (d) => {
    const M = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];
    const i = Number(d);
    return Number.isInteger(i) && i >= 0 && i <= 6 ? M[i] : "—";
  };

  // ================== elementos do formulário (cadastro) ==================
  const elPacienteBusca = $("#paciente_busca");
  const elPacienteNome  = $("#paciente_nome");
  const elPacienteId    = $("#paciente_id");
  const elPacStatus     = $("#paciente_status");
  const elModalidade    = $("#modalidade_select");
  const elContratoWrap  = $("#ag_contrato_wrap");
  const elContrato      = $("#ag_contrato");
  const elContratoAviso = $("#ag_contrato_aviso");
  const elSug           = $("#sugestoes");
  const elMsg           = $("#msg");

  const elProf          = $("#profissional_select");
  const elDia           = $("#dia");
  const elHoraDe        = $("#hora_de");
  const elHoraAte       = $("#hora_ate");
  const elQtd           = $("#qtd");
  const elValor         = $("#valor");
  const elBtnSalvar     = $("#btnSalvar");
  const elBtnSalvarVago = $("#btnSalvarVago");

  // ================== elementos do modal de edição ==================
  const dlgEdit           = $("#modal-agenda-editar");
  const formEdit          = $("#form-agenda-editar");
  const elEditId          = $("#ag_edit_id");
  const elEditPaciente    = $("#ag_edit_paciente");
  const elEditProf        = $("#ag_edit_profissional");
  const elEditDia         = $("#ag_edit_dia");
  const elEditHoraDe      = $("#ag_edit_hora_de");
  const elEditHoraAte     = $("#ag_edit_hora_ate");
  const elEditQtd         = $("#ag_edit_qtd");
  const elEditValor       = $("#ag_edit_valor");
  const elEditMsg         = $("#ag_edit_msg");
  const elEditResumo      = $("#ag_edit_resumo");
  const elEditTrocar      = $("#ag_edit_trocar");
  const elEditVincMod     = $("#ag_edit_vinculo_form_mod");
  const elEditVincCtr     = $("#ag_edit_vinculo_form_ctr");
  const elEditModalidade  = $("#ag_edit_modalidade");
  const elEditContrato    = $("#ag_edit_contrato");
  const elEditContratoAv  = $("#ag_edit_contrato_aviso");
  const elBtnSalvarEdicao = $("#btnAgendaSalvarEdicao");

  // ================== elementos dos filtros/lista ==================
  const elFProf     = $("#f_profissional");
  const elFDia      = $("#f_dia");
  const elFHoraDe   = $("#f_hora_de");
  const elFHoraAte  = $("#f_hora_ate");
  const elFPaciente = $("#f_paciente");
  const elFIdadeMin = $("#f_idade_min");
  const elFIdadeMax = $("#f_idade_max");
  const elFCid      = $("#f_cid");

  const elBtnAplicar   = $("#btnAplicarFiltros");
  const elBtnLimpar    = $("#btnLimparFiltros");
  const elFiltrosMsg   = $("#filtros_msg");

  // lista em cards
  const elCardsList    = $("#agCardsList");
  const elHelper       = $("#agregadosHelper");
  const elBtnRecarregar= $("#btnRecarregar");
  const elAgCount      = $("#agCount"); // pode não existir — protegemos abaixo

  // paginação
  const elPageInfo  = $("#pageInfo");
  const elBtnFirst  = $("#btnFirst");
  const elBtnPrev   = $("#btnPrev");
  const elBtnNext   = $("#btnNext");
  const elBtnLast   = $("#btnLast");
  const elPageInput = $("#pageInput");

  const cardList  = elCardsList?.closest(".card");
  const PAGE_SIZE = Number(cardList?.dataset?.pagesize || 20);

  let cacheItems  = [];
  let currentPage = 1;
  let totalPages  = 1;

  // ================== helpers modal ==================
  function openModal(mod) {
    const el = typeof mod === "string" ? document.getElementById(mod) : mod;
    if (!el) return;
    el.classList.add("is-open");
  }

  function closeModal(mod) {
    const el = typeof mod === "string" ? document.getElementById(mod) : mod;
    if (!el) return;
    el.classList.remove("is-open");
  }

  // ================== carregar profissionais ==================
  async function loadProfissionais() {
    try {
      const res = await fetch(ENDPOINT_PROS);
      const data = await res.json();

      console.debug("[agenda] /api/profissionais retornou:", data);

      const fillSelect = (select, addTodos = false) => {
        if (!select) return;
        const keepFirst = addTodos
          ? `<option value="">Todos</option>`
          : `<option value="">Selecione…</option>`;

        select.innerHTML = keepFirst + data.map(p => {
          const nome = p.nome || p.NOME || "";
          const cpf  = p.cpf  || p.CPF  || p.cpf_digits || "";
          return `<option value="${cpf}">${nome}</option>`;
        }).join("");
      };

      fillSelect(elProf, false);
      fillSelect(elFProf, true);
      fillSelect(elEditProf, false);

      // ===== auto-seleção do profissional logado =====
      const cpfMetaDigits = onlyDigits(CURRENT_PROF_CPF);

      const autoSelectByCpf = (select, label) => {
        if (!select || !cpfMetaDigits) return;
        const opts = Array.from(select.options || []);
        const match = opts.find(o => onlyDigits(o.value) === cpfMetaDigits);

        if (match && match.value !== "") {
          select.value = match.value;
          console.info(`[agenda] ${label} pré-selecionado:`, match.textContent, "| value:", match.value);
        } else {
          console.warn(
            `[agenda] NÃO consegui pré-selecionar ${label}.`,
            "cpfMetaDigits =", cpfMetaDigits,
            "options =", opts.map(o => ({ text: o.textContent, value: o.value }))
          );
        }
      };

      // cadastral (form de criação)
      autoSelectByCpf(elProf, "profissional (cadastro)");
      // filtros
      autoSelectByCpf(elFProf, "filtro profissional");

      // (opcional) edição: só faz sentido ao abrir modal, então deixamos para lá

    } catch (e) {
      console.error("profissionais failed", e);
    }
  }

  // ================== contratos do paciente (usado no formulario e no modal) ==================
  async function buscarContratos(pacienteId, modalidade) {
    const base = ENDPOINT_PAC_BUSCA.replace(/\/$/, "");
    const url = new URL(`${base}/${encodeURIComponent(pacienteId)}/contratos`, location.origin);
    if (modalidade) url.searchParams.set("modalidade", modalidade);
    const res = await fetch(url.toString());
    const data = await res.json().catch(() => null);
    if (!res.ok || !Array.isArray(data)) {
      throw new Error((data && data.error) || "Falha ao carregar contratos.");
    }
    return data;
  }

  function textoContrato(c) {
    const nome = c.nome || modalidadeLabel(c.tipo) || "Contrato";
    const sess = `${c.sessoes_usadas}/${c.sessoes_contratadas} sessões`;
    const papel = c.papel === "beneficiario"
      ? ` · beneficiário${c.titular_nome ? " de " + c.titular_nome : ""}`
      : "";
    return `${nome} · ${sess}${papel}`;
  }

  // Preenche um <select> de contrato. `selecionado` = contrato ja gravado (mantido mesmo que
  // nao esteja mais entre os ativos, para nao ser apagado sem querer).
  // Devolve { lista, erro } ou null se o usuario mudou paciente/modalidade no meio do caminho.
  async function preencherSelectContrato(selectEl, avisoEl, pacienteId, modalidade, selecionado, aindaValido) {
    const SEM = `<option value="">Sem contrato vinculado</option>`;
    selectEl.innerHTML = SEM;
    selectEl.disabled = true;
    avisoEl.classList.remove("is-ok", "is-aviso", "is-erro");
    avisoEl.textContent = "Carregando contratos…";

    let lista = [];
    let erro = null;
    try {
      lista = await buscarContratos(pacienteId, modalidade);
    } catch (e) {
      erro = e;
    }
    if (aindaValido && !aindaValido()) return null;

    const opcoes = lista.map((c) =>
      `<option value="${esc(c.id)}">${esc(textoContrato(c))}</option>`
    );
    const idSel = selecionado != null && selecionado !== "" ? String(selecionado) : "";
    if (idSel && !lista.some((c) => String(c.id) === idSel)) {
      opcoes.push(`<option value="${esc(idSel)}">Contrato #${esc(idSel)} · não consta entre os ativos</option>`);
    }
    selectEl.innerHTML = SEM + opcoes.join("");
    selectEl.disabled = false;

    if (erro) {
      avisoEl.textContent = "Não foi possível carregar os contratos. Você pode salvar mesmo assim, sem contrato.";
      avisoEl.classList.add("is-erro");
    } else if (idSel) {
      selectEl.value = idSel;
      avisoEl.textContent = "";
    } else if (!lista.length) {
      avisoEl.textContent = "Sem contrato ativo. Você pode salvar mesmo assim.";
      avisoEl.classList.add("is-aviso");
    } else if (lista.length === 1) {
      selectEl.value = String(lista[0].id);
      avisoEl.textContent = "Contrato pré-selecionado (único ativo).";
      avisoEl.classList.add("is-ok");
    } else {
      avisoEl.textContent = `${lista.length} contratos ativos: escolha um ou deixe sem vínculo.`;
    }
    return { lista, erro };
  }

  // ================== autocomplete paciente ==================
  let buscaSeq = 0;          // descarta respostas de buscas antigas
  let contratoSeq = 0;       // idem para o seletor de contrato do formulario

  function hideSuggest() {
    if (!elSug) return;
    elSug.classList.add("hidden");
    elSug.innerHTML = "";
  }

  function setPacStatus(texto, tipo) {
    if (!elPacStatus) return;
    elPacStatus.textContent = texto || "";
    elPacStatus.className = "ag-hint" + (tipo ? ` is-${tipo}` : "");
  }

  function limparSelecaoPaciente() {
    if (elPacienteNome) elPacienteNome.value = "";
    if (elPacienteId)   elPacienteId.value = "";
  }

  // `comId` = true quando a lista veio do endpoint novo (tem id); false = reserva (so nome)
  function renderSuggest(list, comId = true) {
    if (!elSug) return;
    if (!list || !list.length) {
      hideSuggest();
      return;
    }

    // homonimos: mesmo nome (sem acento/caixa) aparecendo mais de uma vez na lista
    const contagem = {};
    list.forEach((it) => { const k = chaveNome(it.nome); contagem[k] = (contagem[k] || 0) + 1; });

    const html = `
      <div class="suggest-list">
        ${list.map(it => {
          const nome  = (it.nome || "").toString();
          const homonimo = comId && contagem[chaveNome(nome)] > 1;
          const idade = it.idade != null ? `${it.idade} anos` : "idade —";
          let sub;
          if (comId) {
            const partes = [];
            if (homonimo) partes.push(`<span class="ag-sug-homonimo">Homônimo</span>`);
            partes.push(esc(idade));
            if (homonimo) {
              const nasc = dataBR(it.nascimento);
              if (nasc) partes.push(`nasc. ${esc(nasc)}`);
              partes.push(it.cpf ? `CPF ${esc(it.cpf)}` : "CPF não informado");
            }
            if (it.prontuario) partes.push(`Pront.: ${esc(it.prontuario)}`);
            sub = partes.join(" • ");
          } else {
            const cpf = it.cpf ? `${it.cpf}` : "CPF —";
            sub = esc(`${idade} • ${cpf}${it.prontuario ? ` • Pront.: ${it.prontuario}` : ""}`);
          }
          return `
            <div class="suggest-item" data-nome="${encodeURIComponent(nome)}" data-id="${comId && it.id != null ? esc(it.id) : ""}">
              <span class="title">${esc(nome)}</span>
              <span class="sub">${sub}</span>
            </div>
          `;
        }).join("")}
      </div>
    `;
    elSug.innerHTML = html;
    elSug.classList.remove("hidden");

    $$(".suggest-item", elSug).forEach(item => {
      item.addEventListener("click", () => {
        const nome = decodeURIComponent(item.dataset.nome || "");
        const id   = item.dataset.id || "";
        if (elPacienteBusca) elPacienteBusca.value = nome;
        if (elPacienteNome)  elPacienteNome.value  = nome;
        if (elPacienteId)    elPacienteId.value    = id;
        hideSuggest();
        if (id) {
          setPacStatus(`✔ Paciente selecionado (ID ${id}).`, "ok");
        } else {
          setPacStatus("Paciente escolhido sem ID (modo texto): será localizado pelo nome.", "aviso");
        }
        atualizarContratosForm();
      });
    });
  }

  // Ao DIGITAR, a escolha anterior cai na hora (nao depois do debounce): senao um "Salvar" rapido
  // mandaria o ID antigo junto com o nome novo que esta na tela.
  function onPacienteDigitou() {
    if (!elPacienteBusca) return;
    const eraSelecionado = !!(elPacienteId?.value || elPacienteNome?.value);
    limparSelecaoPaciente();
    if (eraSelecionado) {
      setPacStatus("");
      atualizarContratosForm();
    }
    buscarPacientes();
  }

  // Ao FOCAR o campo ja escolhido (texto igual ao paciente escolhido) mantem a escolha.
  function onPacienteFocou() {
    if (!elPacienteBusca) return;
    const escolhido = (elPacienteNome?.value || "").trim();
    if (escolhido && (elPacienteBusca.value || "").trim() === escolhido) return;
    buscarPacientes();
  }

  const buscarPacientes = debounce(async () => {
    if (!elPacienteBusca) return;
    const q = (elPacienteBusca.value || "").trim();
    if (elPacienteId?.value || elPacienteNome?.value) return; // escolheu na lista enquanto esperava
    if (q.length < 3) {
      setPacStatus("");
      hideSuggest();
      return;
    }
    setPacStatus("Sem seleção da lista: o paciente será localizado pelo nome.", "aviso");
    const seq = ++buscaSeq;
    try {
      const url = new URL(ENDPOINT_PAC_BUSCA, location.origin);
      url.searchParams.set("q", q);
      const res = await fetch(url.toString());
      const data = await res.json();
      if (!res.ok || !Array.isArray(data)) throw new Error((data && data.error) || "busca indisponível");
      if (seq !== buscaSeq) return;
      renderSuggest(data, true);
    } catch (e) {
      console.error("busca de pacientes (com ID) falhou; usando a busca antiga por nome", e);
      try {
        const url = new URL(ENDPOINT_SUGGEST, location.origin);
        url.searchParams.set("q", q);
        const res = await fetch(url.toString());
        const data = await res.json();
        if (seq !== buscaSeq) return;
        renderSuggest(Array.isArray(data) ? data : [], false);
      } catch (e2) {
        console.error("sugestões pacientes failed", e2);
        if (seq === buscaSeq) hideSuggest();
      }
    }
  }, 300);

  // ================== modalidade / contrato (formulario de cadastro) ==================
  async function atualizarContratosForm() {
    if (!elModalidade || !elContratoWrap || !elContrato) return;
    const modalidade = (elModalidade.value || "").trim();
    const pacId = (elPacienteId?.value || "").trim();
    const seq = ++contratoSeq;

    elContrato.innerHTML = `<option value="">Sem contrato vinculado</option>`;
    elContratoAviso.classList.remove("is-ok", "is-aviso", "is-erro");
    elContratoAviso.textContent = "";

    if (!modalidade) {
      elContratoWrap.hidden = true;
      return;
    }
    elContratoWrap.hidden = false;

    if (!pacId) {
      elContrato.disabled = true;
      elContratoAviso.textContent =
        "Escolha o paciente na lista de busca para ver os contratos. Você pode salvar mesmo assim, sem contrato.";
      return;
    }
    elContrato.disabled = false;
    await preencherSelectContrato(
      elContrato, elContratoAviso, pacId, modalidade, null,
      () => seq === contratoSeq
    );
  }

  // ================== salvar agendamento (novo / vago) ==================
  async function salvarAgendamento(isVago = false) {
    if (!elMsg) return;
    elMsg.textContent = "";

    let paciente_nome = (elPacienteNome?.value || elPacienteBusca?.value || "").trim();
    if (isVago) {
      paciente_nome = "VAGO";
    }

    const profissional_cpf = (elProf?.value || "").trim();
    const dia      = (elDia?.value || "").trim();
    const hora_de  = (elHoraDe?.value || "").trim();
    const hora_ate = (elHoraAte?.value || "").trim();
    const qtd      = Number(elQtd?.value || 1);
    const valor_sessao = (elValor && elValor.value !== "" ? Number(elValor.value) : null);

    if (!paciente_nome && !isVago) {
      elMsg.textContent = "Informe o paciente (use a busca).";
      elPacienteBusca?.focus();
      return;
    }
    if (!profissional_cpf) {
      elMsg.textContent = "Selecione o profissional.";
      elProf?.focus();
      return;
    }
    if (!hora_de) {
      elMsg.textContent = "Informe o horário inicial.";
      elHoraDe?.focus();
      return;
    }

    const payload = {
      paciente_nome,
      profissional_cpf,
      dia,
      hora_de,
      hora_ate: hora_ate || undefined,
      qtd,
      valor_sessao
    };

    // Campos novos: so vao quando existem. Sem eles o payload e identico ao formato antigo.
    const pacienteIdSel = (elPacienteId?.value || "").trim();
    const modalidadeSel = (elModalidade?.value || "").trim();
    const contratoSel   = (elContrato?.value || "").trim();
    if (!isVago) {
      if (pacienteIdSel) payload.paciente_id = Number(pacienteIdSel);
      if (modalidadeSel) {
        payload.modalidade_financeira = modalidadeSel;
        if (contratoSel) payload.contrato_id = Number(contratoSel);
      }
    }

    const btn = isVago ? elBtnSalvarVago : elBtnSalvar;
    if (btn) btn.disabled = true;

    try {
      const res = await fetch(ENDPOINT_SAVE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        elMsg.textContent = data.error || "Erro ao salvar.";
        return;
      }

      const n = (data.criados && data.criados.length) ? data.criados.length : qtd;
      const labelPac = isVago ? "horário VAGO" : paciente_nome;
      const labelMod = !isVago && data.modalidade_financeira
        ? ` (${modalidadeLabel(data.modalidade_financeira)}${data.contrato_id ? " · contrato vinculado" : " · sem contrato"})`
        : "";
      elMsg.textContent = `✅ ${n} sessão(ões) criada(s) para ${labelPac}${labelMod}.`;
      if (!isVago && data.redirect) {
        const a = document.createElement("a");
        a.href = data.redirect;
        a.textContent = " Ver prontuário";
        a.style.marginLeft = "6px";
        a.target = "_blank";
        elMsg.appendChild(a);
      }
      await recarregarAgregados(false);
    } catch (e) {
      console.error(e);
      elMsg.textContent = "Erro de rede ao salvar.";
    } finally {
      if (btn) btn.disabled = false;
      setTimeout(() => { if (elMsg.textContent.startsWith("✅")) elMsg.textContent = ""; }, 5000);
    }
  }

  // ================== filtros / agregados ==================
  function buildAgregadosURL(base = ENDPOINT_AGREG) {
    const url = new URL(base, location.origin);

    const profVal   = (elFProf?.value || "").trim();
    const diaVal    = (elFDia?.value || "").trim();
    const hDeVal    = (elFHoraDe?.value || "").trim();
    const hAteVal   = (elFHoraAte?.value || "").trim();
    const pacVal    = (elFPaciente?.value || "").trim();
    const idadeMin  = (elFIdadeMin?.value || "").trim();
    const idadeMax  = (elFIdadeMax?.value || "").trim();
    const cidVal    = (elFCid?.value || "").trim();

    if (profVal) {
      url.searchParams.set("profissional_cpf", profVal);
      url.searchParams.set("profissional", profVal);
    }
    if (diaVal) {
      url.searchParams.set("dia", diaVal);
      url.searchParams.set("dia_semana", diaVal);
    }
    if (hDeVal) {
      url.searchParams.set("hora_de", hDeVal);
      url.searchParams.set("hora_ini", hDeVal);
    }
    if (hAteVal) {
      url.searchParams.set("hora_ate", hAteVal);
      url.searchParams.set("hora_fim", hAteVal);
    }
    if (pacVal) {
      url.searchParams.set("paciente", pacVal);
      url.searchParams.set("paciente_nome", pacVal);
    }
    if (idadeMin) {
      url.searchParams.set("idade_min", idadeMin);
      url.searchParams.set("idadeDe", idadeMin);
    }
    if (idadeMax) {
      url.searchParams.set("idade_max", idadeMax);
      url.searchParams.set("idadeAte", idadeMax);
    }
    if (cidVal) {
      url.searchParams.set("cid", cidVal);
      url.searchParams.set("cid10", cidVal);
    }

    console.debug("[agenda] URL agregados:", url.toString());
    return url.toString();
  }

  function buildExportURL() {
    return buildAgregadosURL(ENDPOINT_EXPORT);
  }

  // Linha "Modalidade · nome do contrato · usadas/total" do cartao (so quando ha modalidade gravada).
  // Agendamentos antigos (sem modalidade) nao mostram a linha: a regra e nao classificar retroativamente.
  function vinculoCartao(it) {
    const mod = modalidadeLabel(it.modalidade_financeira);
    if (!mod) return null;
    if (!it.contrato_id) return { texto: `${mod} · sem contrato vinculado`, alerta: false };
    const nome = (it.combo_nome || "").trim();
    const usadas = Number(it.sessoes_usadas || 0);
    const total  = Number(it.qtd_sessoes != null ? it.qtd_sessoes : (it.qtd || 0));
    if (!nome && total === 0) {
      // contrato gravado, mas a agenda nao o encontrou ativo (cancelado/encerrado/removido)
      return { texto: `${mod} · contrato #${it.contrato_id} não está ativo`, alerta: true };
    }
    return { texto: `${mod} · ${nome || "contrato #" + it.contrato_id} · ${usadas}/${total}`, alerta: false };
  }

  // ======== renderização em CARDS ========
  function renderCardsPage(items, page, pageSize) {
    if (!elCardsList) return;

    elCardsList.innerHTML = "";
    if (!items.length) {
      if (elHelper) elHelper.textContent = "Nenhum registro encontrado.";
      return;
    }
    if (elHelper) elHelper.textContent = "";

    const start = (page - 1) * pageSize;
    const slice = items.slice(start, start + pageSize);

    const cardsHtml = slice.map((it, i) => {
      const idxCache = start + i;

      const diaLabel = it.dia_label
        || (it.dia_num != null ? DIA_LABEL(it.dia_num) : DIA_LABEL(it.dia));

      const hora     = it.hora_ini || "—";
      const prof     = it.profissional || "—";
      const pac      = it.paciente || "—";
      const qtd      = it.qtd != null ? it.qtd : "—";
      const pront    = it.prontuario || it.paciente_prontuario || "";
      const telefone = it.telefone || it.paciente_telefone || it.celular || "";
      const telefoneHTML = telefonePacienteHTML(telefone);



      const prontBtn = it.paciente_id ? `
        <a class="icon-btn" href="/visualizar/${it.paciente_id}" title="Ver prontuário" target="_blank" aria-label="Ver prontuário">
          <svg viewBox="0 0 24 24"><path d="M3 5h18v14H3zM7 5v14"/></svg>
        </a>
      ` : `
        <button class="icon-btn" title="Prontuário indisponível" disabled aria-disabled="true">
          <svg viewBox="0 0 24 24"><path d="M3 5h18v14H3zM7 5v14"/></svg>
        </button>
      `;

      const editBtn = `
        <button
          class="icon-btn btn-edit"
          title="Editar agendamentos deste grupo"
          aria-label="Editar"
          data-id="${it.any_id || ""}"
          data-idx="${idxCache}"
        >
          <svg viewBox="0 0 24 24">
            <path d="M12 20h9"/><path d="M16.5 3.5l4 4L7 21l-4 1 1-4z"/>
          </svg>
        </button>
      `;

      const dowNum = (it.dia_num != null ? it.dia_num : it.dia);

      const vinc = vinculoCartao(it);
      const vincHTML = vinc ? `
            <div class="ag-card-line ag-card-line--vinculo">
              <span class="label">Modalidade</span>
              <span class="value${vinc.alerta ? " is-alerta" : ""}">${esc(vinc.texto)}</span>
            </div>` : "";

      const delBtn = `
        <button
          class="icon-btn danger btn-del"
          title="Excluir todas as sessões deste grupo"
          aria-label="Excluir grupo"
          data-dow="${dowNum}"
          data-hora="${it.hora_ini}"
          data-prof="${encodeURIComponent(it.profissional || "")}"
          data-pac="${encodeURIComponent(it.paciente || "")}"
          data-pid="${it.paciente_id || ""}"
        >
          <svg viewBox="0 0 24 24">
            <path d="M3 6h18"/><path d="M8 6l1-2h6l1 2"/><path d="M6 6v14h12V6"/>
          </svg>
        </button>
      `;

      return `
        <article class="ag-card" data-cache-index="${idxCache}">
          <header class="ag-card-head">
            <div>
              <div class="ag-card-paciente">${pac}</div>
              ${telefoneHTML}
            </div>
            <div class="ag-card-dia">${diaLabel} • ${hora}</div>
          </header>
          <div class="ag-card-body">
            <div class="ag-card-line">
              <span class="label">Prontuário</span>
              <span class="value">${pront || "—"}</span>
            </div>
            <div class="ag-card-line">
              <span class="label">Qtd. sessões</span>
              <span class="value">${qtd}</span>
            </div>${vincHTML}
            <div class="ag-card-line">
              <span class="label">Profissional</span>
              <span class="value">${prof}</span>
            </div>
          </div>
          <footer class="ag-card-actions">
            ${prontBtn}
            ${editBtn}
            ${delBtn}
          </footer>
        </article>
      `;
    }).join("");

    elCardsList.innerHTML = cardsHtml;
  }

  function updatePagerUI() {
    if (!elPageInfo || !elPageInput) return;
    elPageInfo.textContent = `Página ${currentPage} de ${totalPages}`;
    elPageInput.value = String(currentPage);
    if (elBtnFirst) elBtnFirst.disabled = currentPage <= 1;
    if (elBtnPrev)  elBtnPrev.disabled  = currentPage <= 1;
    if (elBtnNext)  elBtnNext.disabled  = currentPage >= totalPages;
    if (elBtnLast)  elBtnLast.disabled  = currentPage >= totalPages;
  }

  async function recarregarAgregados(resetToFirstPage = true) {
    try {
      if (elHelper) elHelper.textContent = "Carregando…";
      const url = buildAgregadosURL();
      const res = await fetch(url);
      const data = await res.json();
      cacheItems  = Array.isArray(data) ? data : [];
      totalPages  = Math.max(1, Math.ceil(cacheItems.length / PAGE_SIZE));
      currentPage = resetToFirstPage ? 1 : Math.min(currentPage, totalPages);

      renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
      updatePagerUI();

      if (elAgCount) elAgCount.textContent = `(${cacheItems.length})`;
      if (elHelper) elHelper.textContent = cacheItems.length ? "" : "Nenhum registro encontrado.";
    } catch (e) {
      console.error(e);
      if (elHelper) elHelper.textContent = "Falha ao carregar.";
      if (elAgCount) elAgCount.textContent = "(0)";
    }
  }

  function applyFiltersMsg() {
    if (!elFiltrosMsg) return;
    const parts = [];
    if (elFProf?.value) parts.push("Profissional");
    if (elFDia?.value) parts.push("Dia");
    if (elFHoraDe?.value || elFHoraAte?.value) parts.push("Horário");
    if (elFPaciente?.value) parts.push("Paciente");
    if (elFIdadeMin?.value || elFIdadeMax?.value) parts.push("Idade");
    if (elFCid?.value) parts.push("CID");
    elFiltrosMsg.textContent = parts.length ? `Filtros ativos: ${parts.join(", ")}` : "";
  }

  function clearFilters() {
    if (elFProf)     elFProf.value = "";
    if (elFDia)      elFDia.value = "";
    if (elFHoraDe)   elFHoraDe.value = "";
    if (elFHoraAte)  elFHoraAte.value = "";
    if (elFPaciente) elFPaciente.value = "";
    if (elFIdadeMin) elFIdadeMin.value = "";
    if (elFIdadeMax) elFIdadeMax.value = "";
    if (elFCid)      elFCid.value = "";
    if (elFiltrosMsg) elFiltrosMsg.textContent = "";
  }

  // ================== modal de edição: vínculo (modalidade / contrato) ==================
  const editCtx = {
    seq: 0, contratoSeq: 0,
    pacienteId: null,      // paciente_id REAL da linha (GET /api/agendamentos/<id>), nao o do JOIN por nome
    modalidade: "",        // vinculo gravado hoje
    contrato: null,
    podeEditar: false,
    editando: false
  };

  function resumoVinculo(linhas) {
    if (!elEditResumo) return;
    elEditResumo.innerHTML = linhas.map((l) => `<div>${l}</div>`).join("");
  }

  function resetVinculoEdicao() {
    editCtx.pacienteId = null;
    editCtx.modalidade = "";
    editCtx.contrato = null;
    editCtx.podeEditar = false;
    editCtx.editando = false;
    if (elEditTrocar) { elEditTrocar.hidden = true; elEditTrocar.textContent = "Trocar vínculo"; }
    if (elEditVincMod) elEditVincMod.hidden = true;
    if (elEditVincCtr) elEditVincCtr.hidden = true;
    if (elEditModalidade) elEditModalidade.value = "";
    if (elEditContrato) { elEditContrato.innerHTML = `<option value="">Sem contrato vinculado</option>`; elEditContrato.disabled = false; }
    if (elEditContratoAv) { elEditContratoAv.textContent = ""; elEditContratoAv.classList.remove("is-ok", "is-aviso", "is-erro"); }
  }

  async function carregarVinculoEdicao(item) {
    if (!elEditResumo) return;
    const seq = ++editCtx.seq;
    resetVinculoEdicao();

    const vago = !item.paciente || String(item.paciente).trim().toUpperCase() === "VAGO";
    if (vago) {
      resumoVinculo(["Horário VAGO: não tem modalidade nem contrato."]);
      return;
    }
    resumoVinculo(["Carregando vínculo…"]);

    let row;
    try {
      const res = await fetch(`${ENDPOINT_AGEND_BASE}/${encodeURIComponent(item.any_id)}`);
      row = await res.json();
      if (!res.ok || !row || row.error) throw new Error((row && row.error) || "falha");
    } catch (e) {
      if (seq !== editCtx.seq) return;
      console.error("vinculo do agendamento nao carregou", e);
      resumoVinculo(["Não foi possível carregar o vínculo atual. Os demais campos continuam editáveis."]);
      return;
    }
    if (seq !== editCtx.seq) return;

    if (!row.paciente_id) {
      resumoVinculo([
        "Agendamento antigo, sem paciente vinculado por ID (modo texto).",
        "A modalidade só pode ser definida em agendamentos cujo paciente foi escolhido na busca."
      ]);
      return;
    }

    editCtx.pacienteId = Number(row.paciente_id);
    editCtx.modalidade = String(row.modalidade_financeira || "").toLowerCase();
    editCtx.contrato   = row.contrato_id != null ? Number(row.contrato_id) : null;
    editCtx.podeEditar = true;

    if (!editCtx.modalidade) {
      resumoVinculo(["<strong>Modalidade:</strong> sem modalidade (agendamento antigo ou não classificado)."]);
    } else {
      const linhas = [`<strong>Modalidade:</strong> ${esc(modalidadeLabel(editCtx.modalidade))}`];
      if (!editCtx.contrato) {
        linhas.push("<strong>Contrato:</strong> sem contrato vinculado (permitido).");
      } else {
        resumoVinculo(linhas.concat([`<strong>Contrato:</strong> #${esc(editCtx.contrato)} (consultando…)`]));
        let lista = null;
        try {
          lista = await buscarContratos(editCtx.pacienteId, editCtx.modalidade);
        } catch (e) {
          console.error("contratos do paciente nao carregaram", e);
        }
        if (seq !== editCtx.seq) return;
        const c = lista ? lista.find((x) => Number(x.id) === editCtx.contrato) : null;
        if (c) {
          linhas.push(`<strong>Contrato:</strong> ${esc(c.nome || modalidadeLabel(c.tipo))} (#${esc(c.id)})`);
          linhas.push(`<strong>Sessões:</strong> ${esc(c.sessoes_usadas)}/${esc(c.sessoes_contratadas)} usadas · ${esc(c.sessoes_restantes)} restantes`);
          const papel = c.papel === "beneficiario"
            ? `beneficiário${c.titular_nome ? " de " + esc(c.titular_nome) : ""}`
            : "titular";
          linhas.push(`<strong>Situação:</strong> <span class="is-ok">Ativo</span> · paciente ${papel}`);
        } else if (lista) {
          linhas.push(`<strong>Contrato:</strong> #${esc(editCtx.contrato)}`);
          linhas.push(`<strong>Situação:</strong> <span class="is-aviso">não consta entre os contratos ativos do paciente</span> (cancelado, encerrado ou paciente fora do contrato).`);
        } else {
          linhas.push(`<strong>Contrato:</strong> #${esc(editCtx.contrato)}`);
          linhas.push(`<strong>Situação:</strong> <span class="is-aviso">não foi possível consultar o contrato agora</span>.`);
        }
      }
      resumoVinculo(linhas);
    }

    if (elEditTrocar) {
      elEditTrocar.textContent = editCtx.modalidade ? "Trocar vínculo" : "Definir vínculo";
      elEditTrocar.hidden = false;
    }
  }

  async function atualizarContratosEdicao(selecionado) {
    if (!elEditModalidade || !elEditContrato || !elEditContratoAv) return;
    const mod = (elEditModalidade.value || "").trim();
    const seq = ++editCtx.contratoSeq;

    if (!mod) {
      elEditContrato.innerHTML = `<option value="">Sem contrato vinculado</option>`;
      elEditContrato.disabled = true;
      elEditContratoAv.classList.remove("is-ok", "is-aviso", "is-erro");
      elEditContratoAv.textContent = "Sem modalidade: nenhum contrato será vinculado.";
      return;
    }
    elEditContrato.disabled = false;
    await preencherSelectContrato(
      elEditContrato, elEditContratoAv, editCtx.pacienteId, mod, selecionado,
      () => seq === editCtx.contratoSeq && editCtx.editando
    );
  }

  // devolve os campos de vinculo para o PUT, ou null se nada mudou (ai o payload fica identico ao antigo)
  function camposVinculoEdicao() {
    if (!editCtx.podeEditar || !editCtx.editando) return null;
    const modNova = (elEditModalidade?.value || "").trim();
    const ctrNovo = modNova ? (elEditContrato?.value || "").trim() : "";
    const ctrAtual = editCtx.contrato ? String(editCtx.contrato) : "";
    if (modNova === editCtx.modalidade && ctrNovo === ctrAtual) return null;
    return {
      modalidade_financeira: modNova || null,
      contrato_id: ctrNovo ? Number(ctrNovo) : null
    };
  }

  // ================== modal de edição: preencher & salvar ==================
  function preencherModalEdicao(item) {
    if (!dlgEdit) return;
    if (elEditMsg) elEditMsg.textContent = "";

    if (elEditId)       elEditId.value       = item.any_id || "";
    if (elEditPaciente) elEditPaciente.value = item.paciente || "VAGO";

    if (elEditDia) {
      let diaVal = "";
      if (item.dia_num !== undefined && item.dia_num !== null) {
        diaVal = String(item.dia_num);
      } else if (item.dia !== undefined && item.dia !== null && /^\d+$/.test(String(item.dia))) {
        diaVal = String(item.dia);
      }
      elEditDia.value = diaVal;
    }

    if (elEditHoraDe)  elEditHoraDe.value  = item.hora_ini || "";
    if (elEditHoraAte) elEditHoraAte.value = item.hora_fim || item.hora_ate || "";

    if (elEditQtd)   elEditQtd.value   = item.qtd != null ? String(item.qtd) : "1";
    if (elEditValor) elEditValor.value = item.valor_sessao != null ? String(item.valor_sessao) : "";

    if (elEditProf) {
      const profCpf = item.profissional_cpf || item.profissional_cpf_digits || "";
      if (profCpf) {
        elEditProf.value = profCpf;
      } else if (item.profissional) {
        const opts = Array.from(elEditProf.options || []);
        const match = opts.find(o =>
          (o.textContent || "").trim().toUpperCase() === item.profissional.trim().toUpperCase()
        );
        if (match) elEditProf.value = match.value;
      }
    }

    carregarVinculoEdicao(item); // assincrono: o modal abre ja, o resumo preenche em seguida
    openModal(dlgEdit);
  }

  async function salvarEdicaoGrupo(ev) {
    if (ev) ev.preventDefault();
    if (!elEditId || !dlgEdit) return;

    const id = (elEditId.value || "").trim();
    if (!id) {
      if (elEditMsg) elEditMsg.textContent = "ID do agendamento não encontrado.";
      return;
    }

    const dia       = (elEditDia?.value || "").trim();
    const hora_de   = (elEditHoraDe?.value || "").trim();
    const hora_ate  = (elEditHoraAte?.value || "").trim();
    const qtd       = Number(elEditQtd?.value || 1);
    const valor_raw = (elEditValor?.value || "").trim();
    const valor_sessao = valor_raw ? Number(valor_raw) : null;
    const paciente_nome    = (elEditPaciente?.value || "").trim();
    const profissional_cpf = (elEditProf?.value || "").trim();

    if (!hora_de) {
      if (elEditMsg) elEditMsg.textContent = "Informe o horário inicial.";
      elEditHoraDe?.focus();
      return;
    }

    const payload = {
      dia,
      hora_de,
      hora_ate: hora_ate || undefined,
      qtd,
      valor_sessao,
      paciente_nome,
      profissional_cpf: profissional_cpf || undefined
    };

    // vinculo (modalidade/contrato): so entra no payload se o usuario trocou algo
    const vinculo = camposVinculoEdicao();
    if (vinculo) {
      if (vinculo.modalidade_financeira && elEditContrato?.disabled) {
        if (elEditMsg) {
          elEditMsg.textContent = "Aguarde o carregamento dos contratos para salvar o vínculo.";
          elEditMsg.style.color = "#dc2626";
        }
        return;
      }
      Object.assign(payload, vinculo);
    }

    if (elEditMsg) {
      elEditMsg.textContent = "Salvando alterações…";
      elEditMsg.style.color = "#64748b";
    }
    if (elBtnSalvarEdicao) elBtnSalvarEdicao.disabled = true;

    try {
      const res = await fetch(`${ENDPOINT_AGEND_BASE}/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        if (elEditMsg) {
          elEditMsg.textContent = data.error || "Falha ao editar agendamento.";
          elEditMsg.style.color = "#dc2626";
        }
        if (elBtnSalvarEdicao) elBtnSalvarEdicao.disabled = false;
        return;
      }

      if (elEditMsg) {
        elEditMsg.textContent = "✅ Agendamento atualizado com sucesso.";
        elEditMsg.style.color = "#16a34a";
      }
      await recarregarAgregados(false);
      setTimeout(() => closeModal(dlgEdit), 400);
    } catch (e) {
      console.error(e);
      if (elEditMsg) {
        elEditMsg.textContent = "Erro de rede ao editar.";
        elEditMsg.style.color = "#dc2626";
      }
    } finally {
      if (elBtnSalvarEdicao) elBtnSalvarEdicao.disabled = false;
    }
  }

  // ================== eventos ==================
  document.addEventListener("click", (e) => {
    if (elSug && !elSug.contains(e.target) && e.target !== elPacienteBusca) {
      hideSuggest();
    }

    const closeTarget = e.target.closest('[data-close="modal-agenda-editar"]');
    if (closeTarget && dlgEdit) {
      closeModal(dlgEdit);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && dlgEdit?.classList.contains("is-open")) {
      closeModal(dlgEdit);
    }
  });

  if (elPacienteBusca) {
    elPacienteBusca.addEventListener("input", onPacienteDigitou);
    elPacienteBusca.addEventListener("focus", onPacienteFocou);
  }

  if (elModalidade) {
    elModalidade.addEventListener("change", atualizarContratosForm);
  }

  if (elEditTrocar) {
    elEditTrocar.addEventListener("click", async () => {
      if (!editCtx.podeEditar) return;
      editCtx.editando = true;
      if (elEditVincMod) elEditVincMod.hidden = false;
      if (elEditVincCtr) elEditVincCtr.hidden = false;
      elEditTrocar.hidden = true;
      if (elEditModalidade) elEditModalidade.value = editCtx.modalidade;
      await atualizarContratosEdicao(editCtx.contrato);
    });
  }
  if (elEditModalidade) {
    elEditModalidade.addEventListener("change", () => {
      const mod = (elEditModalidade.value || "").trim();
      // voltando para a modalidade original, mantem o contrato gravado; senao recomeca sem contrato
      atualizarContratosEdicao(mod && mod === editCtx.modalidade ? editCtx.contrato : null);
    });
  }

  if (elBtnSalvar) {
    elBtnSalvar.addEventListener("click", (e) => {
      e.preventDefault();
      salvarAgendamento(false);
    });
  }

  if (elBtnSalvarVago) {
    elBtnSalvarVago.addEventListener("click", (e) => {
      e.preventDefault();
      salvarAgendamento(true);
    });
  }

  // filtros
  if (elBtnAplicar) {
    elBtnAplicar.addEventListener("click", async () => {
      applyFiltersMsg();
      await recarregarAgregados(true);
    });
  }
  if (elBtnLimpar) {
    elBtnLimpar.addEventListener("click", async () => {
      clearFilters();
      await recarregarAgregados(true);
    });
  }
  if (elBtnRecarregar) {
    elBtnRecarregar.addEventListener("click", async () => {
      await recarregarAgregados(false);
    });
  }

  // paginação
  if (elBtnFirst) {
    elBtnFirst.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage = 1;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elBtnPrev) {
    elBtnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage -= 1;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elBtnNext) {
    elBtnNext.addEventListener("click", () => {
      if (currentPage < totalPages) {
        currentPage += 1;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elBtnLast) {
    elBtnLast.addEventListener("click", () => {
      if (currentPage < totalPages) {
        currentPage = totalPages;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elPageInput) {
    elPageInput.addEventListener("change", () => {
      const v = Math.max(1, Math.min(totalPages, Number(elPageInput.value || 1)));
      currentPage = v;
      renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
      updatePagerUI();
    });
  }

  // exportar
  const elBtnExport = document.getElementById("btnExport");
  elBtnExport?.addEventListener("click", () => {
    const url = buildExportURL();
    window.location.href = url;
  });

  // ================== ações nos CARDS (editar + excluir grupo) ==================
  if (elCardsList) {
    elCardsList.addEventListener("click", async (ev) => {
      const delBtn  = ev.target.closest(".btn-del");
      const editBtn = ev.target.closest(".btn-edit");

      // ---- EXCLUIR GRUPO ----
      if (delBtn) {
        const dow  = delBtn.getAttribute("data-dow");
        const hora = delBtn.getAttribute("data-hora");
        const prof = decodeURIComponent(delBtn.getAttribute("data-prof") || "");
        const pac  = decodeURIComponent(delBtn.getAttribute("data-pac")  || "");
        const pid  = (delBtn.getAttribute("data-pid") || "").trim();

        const ok = confirm(
          `Excluir TODAS as sessões deste grupo?\n\n${DIA_LABEL(dow)} • ${hora}\nProfissional: ${prof}\nPaciente: ${pac}`
        );
        if (!ok) return;

        delBtn.disabled = true;

        try {
          const url = new URL(ENDPOINT_DELETE_GROUP, location.origin);
          url.searchParams.set("dow", dow);
          url.searchParams.set("hora_ini", hora);
          url.searchParams.set("profissional", prof);
          url.searchParams.set("paciente", pac);
          // separa homonimos: sem o ID a exclusao por nome apagaria os dois pacientes
          if (pid) url.searchParams.set("paciente_id", pid);

          const res  = await fetch(url.toString(), { method: "DELETE" });
          const data = await res.json();

          if (!res.ok || data.error) {
            alert(data.error || "Falha ao excluir grupo.");
            delBtn.disabled = false;
            return;
          }
          await recarregarAgregados(false);
        } catch (e) {
          console.error(e);
          alert("Erro de rede ao excluir grupo.");
          delBtn.disabled = false;
        }
        return;
      }

      // ---- EDITAR GRUPO (abrir modal) ----
      if (editBtn) {
        const idx = Number(editBtn.getAttribute("data-idx") || "-1");
        const item = cacheItems[idx];
        if (!item) {
          alert("Não foi possível localizar o registro para editar.");
          return;
        }
        if (!item.any_id) {
          alert("ID não encontrado para edição.");
          return;
        }
        preencherModalEdicao(item);
      }
    });
  }

  // submit do modal de edição
  if (formEdit && elBtnSalvarEdicao) {
    formEdit.addEventListener("submit", salvarEdicaoGrupo);
  }

  // ================== boot ==================
  (async function boot() {
    await loadProfissionais();   // aqui ele já tenta pré-selecionar pelo CPF
    applyFiltersMsg();
    await recarregarAgregados(true); // já vai chamar api/agregados com ?profissional=...
  })();
})();
