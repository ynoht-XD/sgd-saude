// atendimentos/static/js/historico.js
// Historico de atendimentos em ACORDEAO: coluna 1 = data; coluna 2 = profissional + procedimento (com o codigo);
// clicar na linha expande os detalhes. Os dados vem de UMA chamada (/atendimentos/api/historico): lista + paciente.
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  const digitos = (v) => String(v ?? "").replace(/\D/g, "");

  const toBR = (iso) => (/^\d{4}-\d{2}-\d{2}$/.test(iso || "") ? iso.split("-").reverse().join("/") : (iso || "—"));
  const diaSemana = (iso) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return "";
    const [y, m, d] = iso.split("-").map(Number);
    const nome = new Date(y, m - 1, d).toLocaleDateString("pt-BR", { weekday: "long" });
    return nome.charAt(0).toUpperCase() + nome.slice(1);   // "Terça-feira" (so a primeira letra)
  };
  const idade = (iso) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return "";
    const [y, m, d] = iso.split("-").map(Number); const h = new Date();
    let a = h.getFullYear() - y; if (h.getMonth() + 1 < m || (h.getMonth() + 1 === m && h.getDate() < d)) a--;
    return a >= 0 ? `${a} ano(s)` : "";
  };
  const fmtCPF = (v) => { const d = digitos(v); return d.length === 11 ? d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4") : (String(v ?? "").trim() || "—"); };
  const fmtCNS = (v) => { const d = digitos(v); return d.length === 15 ? d.replace(/(\d{3})(\d{4})(\d{4})(\d{4})/, "$1 $2 $3 $4") : (String(v ?? "").trim() || "—"); };
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = (v ?? "") === "" ? "—" : v; };

  let ITENS = [];
  let PACIENTE_ID = "";

  // ---------------------------------------------------------------- paciente
  function preencherPaciente(p, nomeUrl) {
    set("hxNome", (p && p.nome) || nomeUrl || "—");
    if (!p) return;
    set("hxProntuario", p.prontuario);
    set("hxNascimento", p.nascimento ? `${toBR(p.nascimento)}${idade(p.nascimento) ? " · " + idade(p.nascimento) : ""}` : "");
    set("hxCns", fmtCNS(p.cns));
    set("hxCpf", fmtCPF(p.cpf));
    set("hxMod", p.modalidade);
    set("hxStatus", p.status);
    set("hxCid", p.cid && p.cid !== "-" ? p.cid : "");
  }

  // ---------------------------------------------------------------- etiquetas
  function tagStatus(status) {
    const s = String(status || "").trim();
    if (!s) return "";
    const k = s.toLowerCase();
    const cls = /^(realizado|presente|alta)/.test(k) ? "acd-tag--ok"
      : /^(falt|[óo]bito|desligamento)/.test(k) ? "acd-tag--falta"
      : /^(justificado|remarcado|admiss)/.test(k) ? "acd-tag--alerta" : "";
    return `<span class="acd-tag ${cls}">${esc(s)}</span>`;
  }

  const linkAnexo = (caminho) => {
    const c = String(caminho || "").trim();
    return c && /^[\w\-./ ]+$/.test(c) && !c.includes("..") ? `/${c}`.replace(/^\/+/, "/") : "";   // so caminho relativo simples
  };

  // ---------------------------------------------------------------- um item do acordeao
  function itemHtml(it, aberto) {
    const aid = it.atendimento_id ?? it.id;
    const procs = Array.isArray(it.procedimentos) ? it.procedimentos : [];
    const prof = it.profissional || "—";
    const p1 = procs[0];
    const subProc = p1
      ? `${p1.codigo_sigtap ? `<code>${esc(p1.codigo_sigtap)}</code>` : ""}${esc(p1.procedimento || "")}${procs.length > 1 ? ` <span class="acd-mais">+${procs.length - 1} procedimento(s)</span>` : ""}`
      : `<span class="acd-mais">Sem procedimento registrado</span>`;

    const tags = [tagStatus(it.status), it.cid_codigo ? `<span class="acd-tag acd-tag--info" title="CID do atendimento">CID ${esc(it.cid_codigo)}</span>` : ""].filter(Boolean).join("");

    const procHtml = procs.length
      ? `<ul class="acd-lista-proc">${procs.map((p) => `<li>${p.codigo_sigtap ? `<code>${esc(p.codigo_sigtap)}</code>` : ""}<span>${esc(p.procedimento || "—")}</span></li>`).join("")}</ul>`
      : `<p class="acd-texto acd-texto--vazio">Nenhum procedimento registrado neste atendimento.</p>`;

    const anexo = linkAnexo(it.anexo_atestado);
    const evo = (it.evolucao || "").trim();
    const just = (it.justificativa || "").trim();

    return `
      <article class="acd-item${aberto ? " is-aberto" : ""}" data-aid="${esc(aid)}">
        <button type="button" class="acd-head" id="acd-h-${esc(aid)}" aria-expanded="${aberto ? "true" : "false"}" aria-controls="acd-p-${esc(aid)}">
          <span class="acd-col acd-col--data"><b>${esc(toBR(it.data_atendimento))}</b><small>${esc(diaSemana(it.data_atendimento))}</small></span>
          <span class="acd-col acd-col--main">
            <span class="acd-titulo">${esc(prof)}</span>
            <span class="acd-sub">${subProc}</span>
            ${tags ? `<span class="acd-tags">${tags}</span>` : ""}
          </span>
          <span class="acd-chevron" aria-hidden="true"></span>
        </button>

        <div class="acd-panel" id="acd-p-${esc(aid)}" role="region" aria-labelledby="acd-h-${esc(aid)}"${aberto ? "" : " hidden"}>
          <div class="acd-grid">
            <div class="acd-card">
              <span class="acd-rot">Profissional</span>
              <div class="acd-val">${esc(prof)}
                <small>${it.profissional_cbo ? `CBO ${esc(it.profissional_cbo)}` : "CBO não informado"}${it.profissional_cns ? ` · CNS ${esc(fmtCNS(it.profissional_cns))}` : ""}</small>
              </div>
            </div>
            <div class="acd-card">
              <span class="acd-rot">Diagnóstico (CID do atendimento)</span>
              <div class="acd-val">${it.cid_codigo ? `<span class="acd-cid">${esc(it.cid_codigo)}</span>` : `<span class="acd-val--vazio">Não informado</span>`}</div>
            </div>
            <div class="acd-card">
              <span class="acd-rot">Situação</span>
              <div class="acd-val">${tagStatus(it.status) || `<span class="acd-val--vazio">—</span>`}${just ? `<small>${esc(just)}</small>` : ""}</div>
            </div>
          </div>

          <div class="acd-bloco"><span class="acd-rot">Procedimentos realizados</span>${procHtml}</div>

          <div class="acd-bloco"><span class="acd-rot">Evolução</span>
            ${evo ? `<pre class="acd-texto">${esc(evo)}</pre>` : `<p class="acd-texto acd-texto--vazio">Sem evolução registrada.</p>`}
          </div>

          <div class="acd-acoes">
            <a class="acd-link" href="/atendimentos/${encodeURIComponent(aid)}/documentos">Documentos</a>
            ${anexo ? `<a class="acd-link" href="${esc(anexo)}" target="_blank" rel="noopener">Abrir anexo</a>` : ""}
          </div>
        </div>
      </article>`;
  }

  // ---------------------------------------------------------------- lista
  function renderizar(itens, { abrirPrimeiro = false } = {}) {
    const box = $("#histContainer");
    if (!box) return;
    if (!itens.length) {
      box.innerHTML = `<p class="acd-vazio">${ITENS.length ? "Nenhum atendimento corresponde ao filtro." : "Sem atendimentos cadastrados para este paciente."}</p>`;
      return;
    }
    box.innerHTML = itens.map((it, i) => itemHtml(it, abrirPrimeiro && i === 0)).join("");
  }

  function alternar(head) {
    const item = head.closest(".acd-item");
    const painel = item && $(".acd-panel", item);
    if (!painel) return;
    const abrir = head.getAttribute("aria-expanded") !== "true";
    head.setAttribute("aria-expanded", abrir ? "true" : "false");
    painel.hidden = !abrir;
    item.classList.toggle("is-aberto", abrir);
  }

  function filtrar(q) {
    const t = q.trim().toLowerCase();
    const lista = !t ? ITENS : ITENS.filter((it) => {
      const alvo = [
        it.profissional, it.cid_codigo, it.status, toBR(it.data_atendimento), it.data_atendimento,
        ...(it.procedimentos || []).flatMap((p) => [p.procedimento, p.codigo_sigtap]),
      ].join(" ").toLowerCase();
      return alvo.includes(t);
    });
    renderizar(lista);
  }

  function mensagem(texto) {
    const box = $("#histContainer");
    if (box) box.innerHTML = `<p class="acd-vazio">${esc(texto)}</p>`;
  }

  // ---------------------------------------------------------------- inicio
  document.addEventListener("DOMContentLoaded", async () => {
    const params = new URLSearchParams(location.search);
    PACIENTE_ID = (params.get("paciente_id") || "").trim();
    const nomeUrl = (params.get("paciente_nome") || "").trim();

    $("#histContainer")?.addEventListener("click", (e) => {
      const head = e.target.closest(".acd-head");
      if (head) alternar(head);
    });
    $("#histSearch")?.addEventListener("input", (e) => filtrar(e.target.value));

    if (!/^\d+$/.test(PACIENTE_ID)) {
      mensagem("Selecione um paciente para ver o histórico.");
      return;
    }

    const novo = $("#hxNovo");
    if (novo) novo.href = `/atendimentos/registrar?paciente_id=${encodeURIComponent(PACIENTE_ID)}${nomeUrl ? `&paciente_nome=${encodeURIComponent(nomeUrl)}` : ""}`;
    set("hxNome", nomeUrl);

    try {
      const r = await fetch(`/atendimentos/api/historico?paciente_id=${encodeURIComponent(PACIENTE_ID)}`, { credentials: "same-origin" });
      if (r.status === 403) { mensagem("Você não tem permissão para ver o histórico de atendimentos."); return; }
      const j = await r.json().catch(() => null);
      if (!r.ok || !j?.ok) throw new Error(j?.error || `Erro ${r.status}`);

      if (!j.paciente) { mensagem("Paciente não encontrado nesta clínica."); return; }

      preencherPaciente(j.paciente, nomeUrl);
      ITENS = j.items || [];
      const resumo = $("#hxResumo");
      if (resumo) resumo.textContent = ITENS.length
        ? `${ITENS.length} atendimento(s) · mais recente em ${toBR(ITENS[0].data_atendimento)}`
        : "";
      renderizar(ITENS, { abrirPrimeiro: true });   // o mais recente ja vem aberto
    } catch (e) {
      console.error(e);
      mensagem("Não foi possível carregar o histórico agora.");
    }
  });
})();
