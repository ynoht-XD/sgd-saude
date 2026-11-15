/* Secao "Condicoes ativas (CID)" do Cadastro do paciente: adicionar (sem atendimento) e encerrar.
   Servidor decide tudo (permissao atendimentos:editar, formato/catalogo do CID, sem duplicar 'ativo'); aqui so a interface. */
(function () {
  "use strict";
  var raiz = document.getElementById("cidsAtivos");
  if (!raiz) return;

  var lista = document.getElementById("cidsAtivosLista");
  var vazio = document.getElementById("cidsAtivosVazio");
  var msg = document.getElementById("cidsAtivosMsg");
  var podeGerir = raiz.dataset.podeGerir === "1";
  var urlAdd = raiz.dataset.urlAdicionar;
  var urlResolver = raiz.dataset.urlResolver;      // termina em /0/resolver: troca o 0 pelo id
  var urlCid = raiz.dataset.urlCid;

  function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (m) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]; }); }
  function br(iso) { return /^\d{4}-\d{2}-\d{2}/.test(iso || "") ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : (iso || ""); }
  function aviso(texto, tipo) { msg.textContent = texto || ""; msg.className = "cids-ativos__msg" + (tipo ? " is-" + tipo : ""); }

  function desenhar(itens) {
    lista.innerHTML = (itens || []).map(function (c) {
      return '<li class="cids-ativos__item" data-id="' + esc(c.id) + '">' +
        '<span class="cids-ativos__cid">' + esc(c.cid_codigo) + "</span>" +
        '<span class="cids-ativos__desc">' + esc(c.descricao) + "</span>" +
        '<span class="cids-ativos__desde">desde ' + esc(br(c.data_inicio)) + "</span>" +
        (podeGerir ? '<button type="button" class="cids-ativos__btn" data-acao="encerrar">Encerrar</button>' : "") + "</li>";
    }).join("");
    vazio.hidden = !!(itens && itens.length);
  }

  async function chamar(url, corpo) {
    var resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" }, body: JSON.stringify(corpo || {}) });
    var dados = await resp.json().catch(function () { return null; });
    return { resp: resp, dados: dados };
  }

  // Encerrar com confirmacao INLINE (sem window.confirm): 1o clique pede "Confirmar encerramento" / "Cancelar".
  function pedirConfirmacao(btn) {
    var li = btn.closest("[data-id]");
    btn.hidden = true;
    var box = document.createElement("span");
    box.className = "cids-ativos__confirma";
    box.innerHTML = '<button type="button" class="cids-ativos__btn cids-ativos__btn--perigo" data-acao="confirmar">Confirmar encerramento</button>' +
                    '<button type="button" class="cids-ativos__btn" data-acao="cancelar">Cancelar</button>';
    li.appendChild(box);
    box.querySelector("button").focus();
  }

  async function encerrar(li, btnConfirma) {
    var cid = li.querySelector(".cids-ativos__cid").textContent;
    btnConfirma.disabled = true;
    try {
      var r = await chamar(urlResolver.replace(/\/0\/resolver$/, "/" + encodeURIComponent(li.dataset.id) + "/resolver"));
      if (r.resp.status === 403) { aviso("Você não tem permissão para encerrar condições (é preciso a permissão de atendimento).", "erro"); return; }
      if (r.dados && r.dados.items) desenhar(r.dados.items);
      if (!r.resp.ok) { aviso((r.dados && r.dados.error) || "Não foi possível encerrar agora.", "erro"); return; }
      aviso("Condição " + cid + " encerrada.", "ok");
    } catch (e) { aviso("Não foi possível encerrar agora.", "erro"); }
    finally { btnConfirma.disabled = false; }
  }

  lista.addEventListener("click", function (ev) {
    if (!podeGerir) return;
    var btn = ev.target.closest("[data-acao]");
    if (!btn) return;
    var li = btn.closest("[data-id]");
    var acao = btn.dataset.acao;
    if (acao === "encerrar") pedirConfirmacao(btn);
    else if (acao === "cancelar") { li.querySelector(".cids-ativos__confirma").remove(); var orig = li.querySelector('[data-acao="encerrar"]'); orig.hidden = false; orig.focus(); }
    else if (acao === "confirmar") encerrar(li, btn);
  });

  if (!podeGerir) return;

  var busca = document.getElementById("cidsAtivosBusca");
  var oculto = document.getElementById("cidsAtivosCodigo");
  var caixa = document.getElementById("cidsAtivosSug");
  var add = document.getElementById("cidsAtivosAdd");
  var timer = null;
  var RE = /^[A-Za-z]\d{2}(\.?[0-9A-Za-z]{1,4})?$/;

  busca.addEventListener("input", function () {
    oculto.value = ""; aviso("");
    clearTimeout(timer);
    var q = busca.value.trim();
    if (q.length < 2) { caixa.hidden = true; return; }
    timer = setTimeout(async function () {
      try {
        var resp = await fetch(urlCid + "?q=" + encodeURIComponent(q), { credentials: "same-origin" });
        var dados = await resp.json();
        var itens = Array.isArray(dados.items) ? dados.items : [];
        caixa.innerHTML = itens.length
          ? itens.map(function (it, i) { return '<button type="button" data-i="' + i + '">' + esc(it.label) + "</button>"; }).join("")
          : "<small>Nenhum CID encontrado (a base pode não estar importada). Se souber o código, digite-o.</small>";
        caixa.hidden = false;
        caixa.querySelectorAll("button").forEach(function (b) {
          b.addEventListener("click", function () { var it = itens[Number(b.dataset.i)]; oculto.value = it.codigo; busca.value = it.codigo + " — " + it.descricao; caixa.hidden = true; });
        });
      } catch (e) { caixa.hidden = true; }
    }, 250);
  });
  busca.addEventListener("blur", function () { setTimeout(function () { caixa.hidden = true; }, 180); });
  busca.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); add.click(); } });

  add.addEventListener("click", async function () {
    var texto = busca.value.trim();
    var codigo = oculto.value || (RE.test(texto) ? texto.toUpperCase() : "");
    if (!codigo) { aviso("Escolha um CID da lista de sugestões ou digite o código (ex.: F84.0).", "erro"); busca.focus(); return; }
    add.disabled = true;
    try {
      var r = await chamar(urlAdd, { cid_codigo: codigo });
      if (r.dados && r.dados.items) desenhar(r.dados.items);
      if (r.resp.status === 403) { aviso("Você não tem permissão para adicionar condições (é preciso a permissão de atendimento).", "erro"); return; }
      if (!r.resp.ok) { aviso((r.dados && r.dados.error) || "Não foi possível adicionar agora.", "erro"); return; }
      aviso("Condição " + codigo + " adicionada.", "ok");
      busca.value = ""; oculto.value = "";
    } catch (e) { aviso("Não foi possível adicionar agora.", "erro"); }
    finally { add.disabled = false; }
  });
})();
