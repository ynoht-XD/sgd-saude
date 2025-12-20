/* =========================================================================
   SGD · Pacientes — JS “parrudão” (CARDS)
   Arquivo: pacientes.js
   -------------------------------------------------------------------------
   Recursos:
   - GET limpo dos filtros + sync do Exportar XLS
   - Typeahead com <datalist>: Nome, CID, Modalidade, Terapeuta, CBO
   - Normaliza faixa de idade
   - Autosave por campo (end_prontuario, alergias, aviso) + chips (tags)
   - Toast discreto "Salvo!" / "Erro"
   ========================================================================= */

(() => {
  "use strict";

  /* =======================
     CONFIG (rotas)
     ======================= */
  const API = {
    // sugestões
    nomes:        "/pacientes/api/sugestoes/nomes",          // ?q=
    cids:         "/pacientes/api/sugestoes/cids",           // ?q=
    mods:         "/pacientes/api/sugestoes/modalidades",    // ?q=
    terapeutas:   "/pacientes/api/sugestoes/terapeutas",     // ?q=
    cbos:         "/pacientes/api/sugestoes/cbos",           // ?q=

    // export
    exportarXls:  "/pacientes/exportar_xls",

    // autosave (VOCÊ VAI PLUGAR NO BACKEND)
    // Esperado: POST JSON { id, field, value }  OU { id, field:"tags", value:[...] }
    salvarCampo:  "/pacientes/api/autosave",
  };

  /* =======================
     HELPERS
     ======================= */
  const qs  = (sel, el = document) => el.querySelector(sel);
  const qsa = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  const debounce = (fn, wait = 250) => {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), wait);
    };
  };

  const cleanVal = (v) => (v == null ? "" : String(v).trim());

  function toParams(form) {
    const fd = new FormData(form);
    const params = new URLSearchParams();
    for (const [k, v] of fd.entries()) {
      const val = cleanVal(v);
      if (val !== "") params.set(k, val);
    }
    return params;
  }

  function buildUrl(base, form) {
    const url = new URL(base, window.location.origin);
    const params = toParams(form);
    url.search = params.toString();
    return url.toString();
  }

  function renderDatalistOptions(datalistEl, items, mapper) {
    datalistEl.innerHTML = "";
    const frag = document.createDocumentFragment();
    items.forEach((it) => {
      const opt = document.createElement("option");
      const { value, label } = mapper(it);
      opt.value = value;
      if (label) opt.setAttribute("label", label);
      frag.appendChild(opt);
    });
    datalistEl.appendChild(frag);
  }

  async function safeJson(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status} ao buscar ${url}`);
    return await res.json();
  }

  async function safePostJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        if (j && (j.error || j.message)) msg = j.error || j.message;
      } catch (_) {}
      throw new Error(msg);
    }
    return await res.json().catch(() => ({}));
  }

  function normalizeAgeRange($min, $max) {
    const vMin = cleanVal($min.value);
    const vMax = cleanVal($max.value);

    if (vMin && !vMax) $max.value = vMin;
    if (!vMin && vMax) $min.value = vMax;

    const nMin = Number($min.value);
    const nMax = Number($max.value);
    if (!Number.isNaN(nMin) && !Number.isNaN(nMax) && nMin > nMax) {
      $min.value = String(nMax);
      $max.value = String(nMin);
    }
  }

  function syncExportLink(form, $export) {
    if (!$export) return;
    const url = buildUrl(API.exportarXls, form);
    $export.setAttribute("href", url);
  }

  /* =======================
     TOAST discreto
     ======================= */
  function ensureToast() {
    let el = qs("#toast-mini");
    if (el) return el;

    el = document.createElement("div");
    el.id = "toast-mini";
    el.style.position = "fixed";
    el.style.right = "14px";
    el.style.bottom = "14px";
    el.style.zIndex = "9999";
    el.style.maxWidth = "340px";
    el.style.padding = "10px 12px";
    el.style.borderRadius = "12px";
    el.style.boxShadow = "0 12px 34px rgba(2,6,23,.14)";
    el.style.background = "rgba(15,23,42,.92)";
    el.style.color = "#fff";
    el.style.fontFamily = "system-ui, -apple-system, Segoe UI, sans-serif";
    el.style.fontSize = "13px";
    el.style.fontWeight = "800";
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
    el.style.transition = "opacity .18s ease, transform .18s ease";
    el.style.pointerEvents = "none";
    document.body.appendChild(el);
    return el;
  }

  let toastTimer = null;
  function toast(msg, type = "ok") {
    const el = ensureToast();
    el.textContent = msg;

    // corzinha sutil por tipo
    if (type === "ok") el.style.background = "rgba(2, 122, 72, .92)";
    else if (type === "warn") el.style.background = "rgba(180, 83, 9, .92)";
    else el.style.background = "rgba(153, 27, 27, .92)";

    el.style.opacity = "1";
    el.style.transform = "translateY(0)";

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(8px)";
    }, 1400);
  }

  /* =======================
     TYPEAHEAD (datalist)
     ======================= */
  function bindTypeahead(inputSel, datalistSel, url, mapItem, minLen = 2) {
    const $inp = qs(inputSel);
    const $dl  = qs(datalistSel);
    if (!$inp || !$dl) return;

    const run = debounce(async () => {
      const q = cleanVal($inp.value);
      if (q.length < minLen) {
        $dl.innerHTML = "";
        return;
      }
      try {
        const u = new URL(url, window.location.origin);
        u.searchParams.set("q", q);
        const data = await safeJson(u.toString());
        renderDatalistOptions($dl, Array.isArray(data) ? data : [], mapItem);
      } catch (_) {
        // silencioso
      }
    }, 280);

    ["input", "change"].forEach((ev) => $inp.addEventListener(ev, run));
  }

  /* =======================
     AUTOSAVE
     - inputs: data-autosave="<campo>"
     - tags:   data-autosave="tag" + data-tag="<key>"
     ======================= */

  // estado local: tags por paciente (pra enviar array inteiro)
  const TAGS_BY_ID = new Map(); // id -> Set(tags)

  function collectTagsForPatient(id) {
    const card = qs(`.pac-card[data-id="${CSS.escape(String(id))}"]`);
    if (!card) return [];
    const checks = qsa(`input.chip-check[data-autosave="tag"][data-id="${CSS.escape(String(id))}"]`, card);
    return checks.filter(c => c.checked).map(c => c.dataset.tag).filter(Boolean);
  }

  const sendSave = debounce(async (payload, elHint) => {
    try {
      await safePostJson(API.salvarCampo, payload);
      // feedback visual discreto no input/chip
      if (elHint) {
        elHint.classList.add("is-saved");
        setTimeout(() => elHint.classList.remove("is-saved"), 500);
      }
      toast("Salvo!", "ok");
    } catch (err) {
      toast(`Erro ao salvar: ${err.message || "falhou"}`, "err");
    }
  }, 260);

  function bindAutosave() {
    // inputs texto (end_prontuario/alergias/aviso)
    const inputs = qsa("[data-autosave]:not([data-autosave='tag'])");
    inputs.forEach((inp) => {
      const field = inp.dataset.autosave;
      const id    = inp.dataset.id;

      if (!field || !id) return;

      const handler = debounce(() => {
        const value = inp.value ?? "";
        sendSave({ id, field, value }, inp);
      }, 420);

      // salva no blur (mais seguro) e também no change
      inp.addEventListener("blur", handler);
      inp.addEventListener("change", handler);
    });

    // chips (tags)
    const tagChecks = qsa("input.chip-check[data-autosave='tag']");
    tagChecks.forEach((chk) => {
      const id  = chk.dataset.id;
      const tag = chk.dataset.tag;
      if (!id || !tag) return;

      // inicializa mapa
      if (!TAGS_BY_ID.has(id)) {
        TAGS_BY_ID.set(id, new Set(collectTagsForPatient(id)));
      }

      chk.addEventListener("change", () => {
        const set = TAGS_BY_ID.get(id) || new Set();
        if (chk.checked) set.add(tag);
        else set.delete(tag);
        TAGS_BY_ID.set(id, set);

        // envia array inteiro (mais consistente)
        const value = Array.from(set);
        sendSave({ id, field: "tags", value }, chk.parentElement || chk);
      });
    });
  }

  /* =======================
     BOOT
     ======================= */
  document.addEventListener("DOMContentLoaded", () => {
    const $form       = qs("form.filtros-form");
    const $exportLink = qs(".botao-exportar");
    const $idadeMin   = qs('input[name="idade_min"]');
    const $idadeMax   = qs('input[name="idade_max"]');

    // 1) Normalização da idade
    if ($idadeMin && $idadeMax) {
      const handler = () => normalizeAgeRange($idadeMin, $idadeMax);
      ["blur", "change"].forEach((ev) => {
        $idadeMin.addEventListener(ev, handler);
        $idadeMax.addEventListener(ev, handler);
      });
    }

    // 2) Sync do export
    if ($form && $exportLink) {
      const sync = () => syncExportLink($form, $exportLink);
      sync();
      $form.addEventListener("input", debounce(sync, 180));
      $form.addEventListener("change", debounce(sync, 40));
    }

    // 3) Submit GET limpo
    if ($form) {
      $form.addEventListener("submit", (e) => {
        e.preventDefault();
        if ($idadeMin && $idadeMax) normalizeAgeRange($idadeMin, $idadeMax);

        const url = buildUrl(window.location.pathname, $form);
        window.location.assign(url);
      });
    }

    // 4) Typeahead
    // se seu blueprint estiver em /pacientes e você quiser relativo, troque para:
    // API.nomes = "api/sugestoes/nomes"; etc.
    bindTypeahead(
      'input[name="nome"]',
      "#dl-nomes",
      API.nomes,
      (obj) => {
        const cpf   = obj?.cpf ? obj.cpf : "";
        const idade = (obj?.idade ?? "") !== "" && obj?.idade != null ? `${obj.idade} anos` : "";
        const pront = obj?.prontuario ? `Pront: ${obj.prontuario}` : "";
        const parts = [cpf, idade, pront].filter(Boolean);
        return { value: obj?.nome ?? "", label: parts.join(" • ") };
      },
      3
    );

    bindTypeahead(
      'input[name="cid"]',
      "#dl-cids",
      API.cids,
      (it) => {
        if (typeof it === "string") return { value: it, label: "" };
        const cid  = it?.cid ?? "";
        const desc = it?.desc ?? "";
        return { value: cid || desc, label: cid && desc ? `${cid} • ${desc}` : (desc || "") };
      },
      2
    );

    bindTypeahead(
      'input[name="mod"]',
      "#dl-mods",
      API.mods,
      (it) => {
        if (typeof it === "string") return { value: it, label: "" };
        const nome = it?.nome ?? it?.mod ?? "";
        return { value: nome, label: "" };
      },
      2
    );

    bindTypeahead(
      'input[name="terapeuta"]',
      "#dl-terapeutas",
      API.terapeutas,
      (it) => {
        if (typeof it === "string") return { value: it, label: "" };
        const nome = it?.nome ?? it?.terapeuta ?? "";
        return { value: nome, label: "" };
      },
      2
    );

    bindTypeahead(
      'input[name="cbo"]',
      "#dl-cbos",
      API.cbos,
      (it) => {
        if (typeof it === "string") return { value: it, label: "" };
        const cbo  = it?.cbo ?? it?.codigo ?? "";
        const nome = it?.nome ?? it?.descricao ?? "";
        return { value: cbo || nome, label: cbo && nome ? `${cbo} • ${nome}` : (nome || "") };
      },
      2
    );

    // 5) Autosave (inputs + tags)
    bindAutosave();
  });
})();
