// layout.js
(() => {
  "use strict";

  const MOBILE_MAX = 768;

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const body = document.body;
  const sidebar = $("#sidebar");
  const overlay = $("#sidebarOverlay");
  const mobileBtn = $("#mobileMenuBtn");
  const sidebarToggleBtn = $("#sidebarToggleBtn");

  if (!sidebar) return;

  let desktopExpanded = false;

  function isMobile() {
    return window.innerWidth <= MOBILE_MAX;
  }

  function normalizePath(path) {
    if (!path) return "/";
    return path.endsWith("/") && path.length > 1 ? path.slice(0, -1) : path;
  }

  function lockBodyScroll(lock) {
    body.classList.toggle("menu-open", !!lock);
    body.classList.toggle("no-scroll", !!lock);
  }

  // =========================================================
  // DESKTOP SIDEBAR
  // =========================================================
  function collapseDesktopSidebar() {
    if (isMobile()) return;

    sidebar.classList.add("is-collapsed");
    sidebar.classList.remove("is-pinned");
    body.classList.add("sidebar-collapsed");
    desktopExpanded = false;

    // ao recolher, fecha submenus
    getMenuGroups().forEach((group) => setMenuState(group, false));
  }

  function expandDesktopSidebar() {
    if (isMobile()) return;

    sidebar.classList.remove("is-collapsed");
    sidebar.classList.add("is-pinned");
    body.classList.remove("sidebar-collapsed");
    desktopExpanded = true;
  }

  // =========================================================
  // MOBILE SIDEBAR
  // =========================================================
  function openMobileSidebar() {
    if (!isMobile()) return;

    sidebar.classList.add("is-mobile-open");
    overlay?.classList.add("is-visible");
    lockBodyScroll(true);
  }

  function closeMobileSidebar() {
    sidebar.classList.remove("is-mobile-open");
    overlay?.classList.remove("is-visible");
    lockBodyScroll(false);

    // opcional: fecha submenus ao sair do mobile
    getMenuGroups().forEach((group) => setMenuState(group, false));
  }

  function toggleMobileSidebar(force) {
    const shouldOpen =
      typeof force === "boolean"
        ? force
        : !sidebar.classList.contains("is-mobile-open");

    if (shouldOpen) openMobileSidebar();
    else closeMobileSidebar();
  }

  // =========================================================
  // SUBMENUS
  // =========================================================
  function getMenuGroups() {
    return $$(".menu-group", sidebar);
  }

  function setMenuState(group, open) {
    if (!group) return;

    const toggle = $(".menu-toggle", group);
    const submenu = $(".submenu", group);

    if (!toggle || !submenu) return;

    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.classList.toggle("is-open", !!open);
    group.classList.toggle("is-open", !!open);
    submenu.classList.toggle("open", !!open);

    if (open) {
      submenu.removeAttribute("hidden");
      submenu.style.maxHeight = submenu.scrollHeight + "px";
      submenu.style.opacity = "1";
    } else {
      submenu.setAttribute("hidden", "");
      submenu.style.maxHeight = "0px";
      submenu.style.opacity = "0";
    }
  }

  function closeSiblingMenus(currentGroup) {
    getMenuGroups().forEach((group) => {
      if (group !== currentGroup) {
        setMenuState(group, false);
      }
    });
  }

  function initMenus() {
    const currentPath = normalizePath(window.location.pathname);

    getMenuGroups().forEach((group) => {
      const toggle = $(".menu-toggle", group);
      const submenu = $(".submenu", group);
      if (!toggle || !submenu) return;

      const submenuLinks = $$("a[href]", submenu);

      const hasActiveChild = submenuLinks.some((link) => {
        const href = link.getAttribute("href");
        if (!href || href === "#") return false;

        try {
          const url = new URL(href, window.location.origin);
          return normalizePath(url.pathname) === currentPath;
        } catch (_) {
          return false;
        }
      });

      setMenuState(group, hasActiveChild);

      toggle.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();

        // no desktop, ao clicar submenu, garante que sidebar fique expandida
        if (!isMobile()) {
          expandDesktopSidebar();
        }

        const currentlyOpen = toggle.getAttribute("aria-expanded") === "true";
        const willOpen = !currentlyOpen;

        closeSiblingMenus(group);
        setMenuState(group, willOpen);
      });

      toggle.addEventListener("keydown", (e) => {
        const currentlyOpen = toggle.getAttribute("aria-expanded") === "true";

        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle.click();
        }

        if (e.key === "ArrowRight" && !currentlyOpen) {
          closeSiblingMenus(group);
          setMenuState(group, true);
        }

        if (e.key === "ArrowLeft" && currentlyOpen) {
          setMenuState(group, false);
        }
      });
    });
  }

  // =========================================================
  // LINK ATIVO
  // =========================================================
  function markActiveLinks() {
    const currentPath = normalizePath(window.location.pathname);
    const links = $$("a[href]", sidebar);

    links.forEach((link) => {
      const href = link.getAttribute("href");
      if (!href || href === "#") return;

      try {
        const url = new URL(href, window.location.origin);
        const samePath = normalizePath(url.pathname) === currentPath;

        link.classList.toggle("is-active", samePath);

        if (samePath) {
          const parentGroup = link.closest(".menu-group");
          if (parentGroup && !isMobile()) {
            expandDesktopSidebar();
            setMenuState(parentGroup, true);
          }
        }
      } catch (_) {}
    });
  }

  // =========================================================
  // RESPONSIVO
  // =========================================================
  function applyResponsiveMode() {
    if (isMobile()) {
      sidebar.classList.remove("is-collapsed", "is-pinned");
      body.classList.remove("sidebar-collapsed");
      closeMobileSidebar();
    } else {
      closeMobileSidebar();
      collapseDesktopSidebar();
    }
  }

  // =========================================================
  // EVENTOS
  // =========================================================
  function bindGlobalEvents() {
    mobileBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleMobileSidebar();
    });

    sidebarToggleBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (isMobile()) {
        toggleMobileSidebar();
      }
    });

    overlay?.addEventListener("click", () => {
      closeMobileSidebar();
    });

    // desktop: expande no hover e SEGURA aberto
    sidebar.addEventListener("mouseenter", () => {
      if (isMobile()) return;
      if (!desktopExpanded) {
        expandDesktopSidebar();
      }
    });

    // importante:
    // NÃO fecha no mouseleave
    // só fecha no clique fora ou ESC

    // clique fora
    document.addEventListener("click", (e) => {
      const clickedInsideSidebar = sidebar.contains(e.target);
      const clickedMobileBtn = mobileBtn?.contains(e.target);
      const clickedToggleBtn = sidebarToggleBtn?.contains(e.target);

      if (isMobile()) {
        if (
          sidebar.classList.contains("is-mobile-open") &&
          !clickedInsideSidebar &&
          !clickedMobileBtn &&
          !clickedToggleBtn
        ) {
          closeMobileSidebar();
        }
        return;
      }

      if (!clickedInsideSidebar && !clickedMobileBtn && !clickedToggleBtn) {
        collapseDesktopSidebar();
      }
    });

    // impede que clique interno feche a sidebar
    sidebar.addEventListener("click", (e) => {
      e.stopPropagation();

      const link = e.target.closest("a[href]");
      if (!link) return;

      const href = link.getAttribute("href");

      if (isMobile() && href && href !== "#") {
        closeMobileSidebar();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;

      if (isMobile() && sidebar.classList.contains("is-mobile-open")) {
        closeMobileSidebar();
        return;
      }

      if (!isMobile()) {
        collapseDesktopSidebar();
      }
    });

    let resizeTimer = null;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        applyResponsiveMode();
      }, 120);
    });
  }

  // =========================================================
  // BOOT
  // =========================================================
  function boot() {
    applyResponsiveMode();
    initMenus();
    markActiveLinks();
    bindGlobalEvents();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();