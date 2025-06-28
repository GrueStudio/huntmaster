/**
 * layout.js
 * This script manages the interactivity of the main application layout,
 * including the collapsible sidebar and its responsive behavior.
 */
document.addEventListener("DOMContentLoaded", () => {
  // --- DOM Element Selectors ---
  const sidebar = document.getElementById("sidebar");
  const sidebarToggleDesktop = document.getElementById(
    "sidebar-toggle-desktop",
  );
  const sidebarToggleMobile = document.getElementById("sidebar-toggle-mobile");
  const sidebarOverlay = document.getElementById("sidebar-overlay");
  const contentArea = document.getElementById("content-area");
  const appContainer = document.getElementById("app-container"); // Select the main app container
  const body = document.body; // Use body for the class toggle for simplicity

  // --- Layout Fix ---
  // The 'flex' and 'flex-row' classes are now directly in _layout.html on #app-container.
  // This removes the need to programmatically add them here, preventing layout FOUC.
  // if (appContainer) {
  //   appContainer.classList.add(
  //     "relative",
  //     "flex",
  //     "h-screen",
  //     "overflow-hidden",
  //   );
  // }
  // --- End Layout Fix ---

  // --- State Management ---
  const SIDEBAR_COLLAPSED_KEY = "sidebarCollapsed";

  // Function to apply the initial state of the sidebar from localStorage
  // This function now primarily toggles the body class and icon,
  // letting CSS handle the margin-left for contentArea.
  const applyInitialSidebarState = () => {
    // On mobile, the sidebar is always off-canvas initially.
    if (window.innerWidth < 1024) {
      // Ensure mobile sidebar is hidden and content area has no margin on mobile
      if (sidebar) sidebar.classList.add("-translate-x-full");
      if (sidebarOverlay) sidebarOverlay.classList.add("hidden");
      body.classList.remove("sidebar-collapsed"); // Ensure no collapsed class on mobile
      return;
    }

    if (localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true") {
      body.classList.add("sidebar-collapsed");
      if (sidebarToggleDesktop)
        sidebarToggleDesktop
          .querySelector("i")
          .classList.replace("fa-chevron-left", "fa-chevron-right");
    } else {
      body.classList.remove("sidebar-collapsed");
      if (sidebarToggleDesktop)
        sidebarToggleDesktop
          .querySelector("i")
          .classList.replace("fa-chevron-right", "fa-chevron-left");
    }
    // contentArea.style.marginLeft is now handled by CSS rules in _layout.html
  };

  // --- Event Handlers ---

  // Toggles the sidebar on desktop view (collapse/expand)
  // This function now primarily toggles the body class and icon,
  // letting CSS handle the margin-left for contentArea.
  const handleDesktopToggle = () => {
    body.classList.toggle("sidebar-collapsed");
    const isCollapsed = body.classList.contains("sidebar-collapsed");
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, isCollapsed);

    // Update toggle icon
    if (isCollapsed) {
      if (sidebarToggleDesktop)
        sidebarToggleDesktop
          .querySelector("i")
          .classList.replace("fa-chevron-left", "fa-chevron-right");
    } else {
      if (sidebarToggleDesktop)
        sidebarToggleDesktop
          .querySelector("i")
          .classList.replace("fa-chevron-right", "fa-chevron-left");
    }
    // contentArea.style.marginLeft is now handled by CSS rules in _layout.html
  };

  // Toggles the sidebar on mobile view (off-canvas slide-in/out)
  const handleMobileToggle = () => {
    if (sidebar) sidebar.classList.toggle("-translate-x-full");
    if (sidebarOverlay) sidebarOverlay.classList.toggle("hidden");
  };

  // --- Event Listeners ---
  if (sidebarToggleDesktop) {
    sidebarToggleDesktop.addEventListener("click", handleDesktopToggle);
  }

  if (sidebarToggleMobile) {
    sidebarToggleMobile.addEventListener("click", handleMobileToggle);
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener("click", handleMobileToggle);
  }

  // Adjust layout based on window resize
  window.addEventListener("resize", () => {
    // If resizing to a larger screen, ensure mobile overlay is hidden
    if (window.innerWidth >= 1024) {
      if (sidebar && sidebar.classList.contains("-translate-x-full")) {
        // It shouldn't be translated on desktop, make sure it's visible
        sidebar.classList.remove("-translate-x-full");
      }
      if (sidebarOverlay && !sidebarOverlay.classList.contains("hidden")) {
        sidebarOverlay.classList.add("hidden");
      }
    }
    // Re-apply initial state on resize to ensure correctness across breakpoints
    applyInitialSidebarState();
  });

  // --- Initial Setup ---
  // The initial 'sidebar-collapsed' class is now handled by an inline script in _layout.html
  // for FOUC prevention. This call is still useful for ensuring other initial
  // settings (like icon state) are consistent.
  applyInitialSidebarState();

  // The custom style injection for .sidebar-collapsed is now removed from here
  // and placed directly in the <head> of _layout.html for FOUC prevention.
});
