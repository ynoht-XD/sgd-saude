/* csrf.js — proteção CSRF no front (Flask-WTF).
 *
 * Carregado no <head> do layout.html, ANTES de qualquer outro script, para que
 * todo fetch() da página já passe pelo wrapper.
 *
 *  1) fetch(): em toda requisição não-GET para o MESMO domínio, envia o header
 *     X-CSRFToken (lido da <meta name="csrf-token">).
 *  2) <form method="post">: injeta o campo oculto csrf_token no envio, tanto no
 *     submit normal (fase de captura, antes dos handlers da página) quanto em
 *     form.submit() programático (que não dispara o evento "submit").
 *
 * O token nunca é enviado para outro domínio.
 */
(function () {
  "use strict";

  var SAFE = /^(GET|HEAD|OPTIONS|TRACE)$/i;
  var FIELD = "csrf_token";

  function getToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") || "" : "";
  }

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  // ---------------------------------------------------------------- fetch
  if (typeof window.fetch === "function" && !window.fetch.__csrfWrapped) {
    var nativeFetch = window.fetch.bind(window);

    var wrapped = function (input, init) {
      try {
        var isReq = typeof Request !== "undefined" && input instanceof Request;
        var method = String((init && init.method) || (isReq && input.method) || "GET");

        if (!SAFE.test(method)) {
          var url = isReq ? input.url : String(input);
          var token = getToken();

          if (token && sameOrigin(url)) {
            var src = (init && init.headers) || (isReq ? input.headers : undefined);
            var headers = new Headers(src || {});
            if (!headers.has("X-CSRFToken")) headers.set("X-CSRFToken", token);
            init = Object.assign({}, init || {}, { headers: headers });
          }
        }
      } catch (e) {
        /* em caso de qualquer falha, segue com a chamada original */
      }
      return nativeFetch(input, init);
    };

    wrapped.__csrfWrapped = true;
    window.fetch = wrapped;
  }

  // ---------------------------------------------------------------- forms
  function ensureField(form, methodOverride, actionOverride) {
    if (!form || form.nodeName !== "FORM") return;

    var method = String(methodOverride || form.getAttribute("method") || form.method || "get");
    if (SAFE.test(method) || method.toLowerCase() === "dialog") return;

    var action = actionOverride || form.getAttribute("action") || window.location.href;
    if (!sameOrigin(action)) return;

    var token = getToken();
    if (!token) return;

    var field = form.querySelector('input[name="' + FIELD + '"]');
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = FIELD;
      form.appendChild(field);
    }
    field.value = token;
  }

  // submit normal / requestSubmit — captura: roda antes dos handlers da página
  document.addEventListener(
    "submit",
    function (ev) {
      var sub = ev.submitter;
      ensureField(
        ev.target,
        sub && sub.getAttribute && sub.getAttribute("formmethod"),
        sub && sub.getAttribute && sub.getAttribute("formaction")
      );
    },
    true
  );

  // form.submit() programático não dispara "submit"
  if (window.HTMLFormElement && !HTMLFormElement.prototype.submit.__csrfWrapped) {
    var nativeSubmit = HTMLFormElement.prototype.submit;
    var wrappedSubmit = function () {
      try {
        ensureField(this);
      } catch (e) {}
      return nativeSubmit.apply(this, arguments);
    };
    wrappedSubmit.__csrfWrapped = true;
    HTMLFormElement.prototype.submit = wrappedSubmit;
  }
})();
