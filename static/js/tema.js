// tema.js · UX.3 · botao de tema da topbar (carregado so para MASTER). Cicla Claro -> Escuro -> Sistema.
// Preferencia em localStorage("sgd-theme"). O <head> (templates/_tema_head.html) aplica o tema antes do CSS;
// aqui so tratamos o clique, o rotulo, o modo "Sistema" (matchMedia) e a sincronia entre abas.
(function () {
  "use strict";
  var d = document.documentElement;
  if (d.getAttribute("data-tema-liberado") !== "1") return;
  var btn = document.getElementById("btnTema");
  if (!btn) return;

  var KEY = "sgd-theme";
  var ORDEM = ["light", "dark", "system"];
  var NOMES = { light: "Claro", dark: "Escuro", system: "Sistema" };
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function lerModo() {
    var m = "light";
    try { m = localStorage.getItem(KEY) || "light"; } catch (e) {}
    return ORDEM.indexOf(m) < 0 ? "light" : m;
  }
  function proximo(m) { return ORDEM[(ORDEM.indexOf(m) + 1) % ORDEM.length]; }
  function rotular(m) {
    var t = "Tema: " + NOMES[m] + " (clique para " + NOMES[proximo(m)] + ")";
    btn.setAttribute("aria-label", t);
    btn.setAttribute("title", t);
  }
  function aplicar(m) {
    var escuro = m === "dark" || (m === "system" && mq && mq.matches);
    d.setAttribute("data-theme", escuro ? "dark" : "light");
    d.setAttribute("data-theme-mode", m);
    rotular(m);
  }

  btn.addEventListener("click", function () {
    var m = proximo(lerModo());
    try { localStorage.setItem(KEY, m); } catch (e) {}
    aplicar(m);
  });

  if (mq) {
    var aoMudarSO = function () { if (lerModo() === "system") aplicar("system"); };
    if (mq.addEventListener) mq.addEventListener("change", aoMudarSO);
    else if (mq.addListener) mq.addListener(aoMudarSO);
  }
  window.addEventListener("storage", function (e) { if (e.key === KEY) aplicar(lerModo()); });

  rotular(lerModo());
})();
