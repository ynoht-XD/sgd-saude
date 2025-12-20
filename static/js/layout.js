// layout.js

// ==========================
// Config
// ==========================
const MOBILE_MAX = 768;
const IDLE_CLOSE_MS = 5000;

// ==========================
// Util: trava/destrava scroll do body no mobile
// ==========================
function setBodyScrollLocked(locked) {
  document.body.classList.toggle("no-scroll", !!locked);
}

// ==========================
// Helpers
// ==========================
function isMobile() {
  return window.innerWidth <= MOBILE_MAX;
}

function getSidebar() {
  return document.getElementById("sidebar");
}

function getToggleBtn() {
  const sidebar = getSidebar();
  return sidebar ? sidebar.querySelector(".toggle-btn") : null;
}

// ==========================
// Sidebar: mobile open/close (classe .active)
// ==========================
function openMobileSidebar() {
  const sidebar = getSidebar();
  if (!sidebar) return;
  sidebar.classList.add("active");
  setBodyScrollLocked(true);
}

function closeMobileSidebar() {
  const sidebar = getSidebar();
  if (!sidebar) return;
  sidebar.classList.remove("active");
  setBodyScrollLocked(false);
}

function toggleMobileSidebar() {
  const sidebar = getSidebar();
  if (!sidebar) return;
  if (sidebar.classList.contains("active")) closeMobileSidebar();
  else openMobileSidebar();
}

// ==========================
// Sidebar: desktop collapse/hover + auto-close idle
// ==========================
let idleTimer = null;

function clearIdleTimer() {
  if (idleTimer) {
    clearTimeout(idleTimer);
    idleTimer = null;
  }
}

function startIdleTimer() {
  clearIdleTimer();
  idleTimer = setTimeout(() => {
    const sidebar = getSidebar();
    if (!sidebar) return;
    if (isMobile()) return;

    if (!sidebar.classList.contains("is-pinned")) {
      sidebar.classList.remove("is-hovered");
      sidebar.classList.add("is-collapsed");
    }
  }, IDLE_CLOSE_MS);
}

function toggleDesktopPin() {
  const sidebar = getSidebar();
  if (!sidebar || isMobile()) return;

  const pinned = sidebar.classList.toggle("is-pinned");
  if (pinned) {
    sidebar.classList.remove("is-collapsed");
    sidebar.classList.add("is-hovered");
    clearIdleTimer();
  } else {
    startIdleTimer();
  }
}

// ==========================
// Responsivo: aplica modo correto
// ==========================
function applyMode() {
  const sidebar = getSidebar();
  if (!sidebar) return;

  if (isMobile()) {
    // Mobile: nunca usar estados de desktop
    sidebar.classList.remove("is-collapsed", "is-hovered", "is-pinned");
    // scroll lock coerente
    setBodyScrollLocked(sidebar.classList.contains("active"));
  } else {
    // Desktop: .active é só mobile
    sidebar.classList.remove("active");
    setBodyScrollLocked(false);

    if (!sidebar.classList.contains("is-pinned")) {
      sidebar.classList.add("is-collapsed");
      sidebar.classList.remove("is-hovered");
    }
  }
}

// ==========================
// Boot
// ==========================
document.addEventListener("DOMContentLoaded", () => {
  const sidebar = getSidebar();
  const toggleBtn = getToggleBtn();
  if (!sidebar) return;

  applyMode();

  // Hamburger: mobile abre/fecha; desktop pin/unpin
  if (toggleBtn) {
    toggleBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (isMobile()) toggleMobileSidebar();
      else toggleDesktopPin();
    });
  }

  // Clique fora fecha sidebar no mobile
  window.addEventListener("click", (e) => {
    if (!isMobile()) return;
    if (!sidebar.classList.contains("active")) return;

    const clickedInsideSidebar = sidebar.contains(e.target);
    const clickedToggle = e.target.closest(".toggle-btn");
    if (!clickedInsideSidebar && !clickedToggle) closeMobileSidebar();
  });

  // ESC: fecha mobile e recolhe desktop (se não pinned) + fecha submenus
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;

    if (isMobile() && sidebar.classList.contains("active")) {
      closeMobileSidebar();
    }

    if (!isMobile() && !sidebar.classList.contains("is-pinned")) {
      sidebar.classList.remove("is-hovered");
      sidebar.classList.add("is-collapsed");
    }

    document
      .querySelectorAll(".has-sub.open, .has-sub[aria-expanded='true']")
      .forEach((li) => {
        const { toggleBtn, panel } = resolveSubmenuElements(li);
        if (toggleBtn && panel) setSubmenuState(li, toggleBtn, panel, false);
      });
  });

  // Mobile: clicar em link fecha sidebar
  sidebar.addEventListener("click", (e) => {
    const link = e.target.closest("a");
    if (link && isMobile() && sidebar.classList.contains("active")) {
      closeMobileSidebar();
    }
  });

  // Desktop: hover expande e idle recolhe
  sidebar.addEventListener("mouseenter", () => {
    if (isMobile()) return;

    if (!sidebar.classList.contains("is-pinned")) {
      sidebar.classList.add("is-hovered");
      sidebar.classList.remove("is-collapsed");
    }
    clearIdleTimer();
  });

  sidebar.addEventListener("mouseleave", () => {
    if (isMobile()) return;

    if (!sidebar.classList.contains("is-pinned")) {
      startIdleTimer();
    }
  });

  ["mousemove", "click", "keydown", "wheel"].forEach((evt) => {
    sidebar.addEventListener(evt, () => {
      if (isMobile()) return;
      if (!sidebar.classList.contains("is-pinned")) {
        if (sidebar.classList.contains("is-hovered")) startIdleTimer();
      }
    });
  });

  // Resize: aplica modo correto
  window.addEventListener("resize", applyMode);

  // Submenus
  initAllSubmenus();
});

/* =========================================================================
   Submenus (compatível com .submenu/.sub + acessibilidade + teclado)
   ========================================================================= */

function resolveSubmenuElements(li) {
  if (!li) return { toggleBtn: null, panel: null };

  let toggleBtn =
    li.querySelector(":scope > .submenu-toggle") ||
    li.querySelector(":scope > a[href^='javascript']") ||
    li.querySelector(":scope > a:not([href])") ||
    li.querySelector(":scope > a");

  let panel =
    li.querySelector(":scope > .submenu") ||
    li.querySelector(":scope > .sub") ||
    li.querySelector(":scope > ul");

  if (panel && panel.tagName !== "UL") {
    const ul = li.querySelector(":scope > ul");
    if (ul) panel = ul;
  }

  return { toggleBtn, panel };
}

function setSubmenuState(li, toggleBtn, panel, expanded) {
  const isOpen = !!expanded;

  li.classList.toggle("open", isOpen);

  toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  li.setAttribute("aria-expanded", isOpen ? "true" : "false");

  if (isOpen) panel.removeAttribute("hidden");
  else panel.setAttribute("hidden", "");
}

function initAllSubmenus() {
  const roots = document.querySelectorAll(".menu, .nav, #sidebar, #sidebar .menu");
  const seen = new Set();

  roots.forEach((root) => {
    root.querySelectorAll(".has-sub").forEach((li) => {
      if (seen.has(li)) return;
      seen.add(li);

      const { toggleBtn, panel } = resolveSubmenuElements(li);
      if (!toggleBtn || !panel) return;

      toggleBtn.setAttribute("aria-expanded", "false");
      li.setAttribute("aria-expanded", "false");
      panel.setAttribute("hidden", "");

      toggleBtn.addEventListener("click", (e) => {
        if (toggleBtn.tagName === "A") e.preventDefault();

        // Se clicar em submenu no desktop enquanto colapsado, expande “no hover”
        const sidebar = getSidebar();
        if (sidebar && !isMobile() && sidebar.classList.contains("is-collapsed")) {
          sidebar.classList.add("is-hovered");
          sidebar.classList.remove("is-collapsed");
          startIdleTimer();
        }

        const currentlyOpen = toggleBtn.getAttribute("aria-expanded") === "true";
        const wantOpen = !currentlyOpen;

        closeSiblings(li);
        setSubmenuState(li, toggleBtn, panel, wantOpen);
      });

      toggleBtn.addEventListener("keydown", (e) => {
        const currentlyOpen = toggleBtn.getAttribute("aria-expanded") === "true";

        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggleBtn.click();
        } else if (e.key === "ArrowRight" && !currentlyOpen) {
          setSubmenuState(li, toggleBtn, panel, true);
        } else if (e.key === "ArrowLeft" && currentlyOpen) {
          setSubmenuState(li, toggleBtn, panel, false);
        }
      });

      const current = panel.querySelector(`a[href="${location.pathname}"]`);
      if (current) setSubmenuState(li, toggleBtn, panel, true);
    });
  });
}

function closeSiblings(li) {
  const parent = li.parentElement;
  if (!parent) return;

  parent
    .querySelectorAll(":scope > .has-sub.open, :scope > .has-sub[aria-expanded='true']")
    .forEach((sib) => {
      if (sib === li) return;
      const { toggleBtn, panel } = resolveSubmenuElements(sib);
      if (toggleBtn && panel) setSubmenuState(sib, toggleBtn, panel, false);
    });
}
