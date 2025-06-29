document.addEventListener("DOMContentLoaded", () => {
  const dashboardGrid = document.getElementById("dashboard-grid");
  const toggleLockButton = document.getElementById("toggle-lock-button");

  // Constants for localStorage key
  const CARD_ORDER_KEY = "dashboardCardOrder";
  const LAYOUT_LOCKED_KEY = "dashboardLayoutLocked";

  let draggedItem = null; // To store the currently dragged card element

  /**
   * Updates the draggable state of all cards based on the locked status.
   * @param {boolean} isLocked - True if layout is locked, false if unlocked.
   */
  const updateCardDraggableState = (isLocked) => {
    const cards = dashboardGrid.querySelectorAll(".dashboard-card");
    cards.forEach((card) => {
      card.draggable = !isLocked; // If locked, draggable is false; if unlocked, draggable is true
      if (isLocked) {
        card.classList.remove(
          "cursor-grabbing",
          "hover:border-blue-500",
          "border-blue-500",
        );
        card.classList.add("cursor-grab"); // Still show grab, but dragging won't work
      } else {
        card.classList.add("cursor-grabbing");
        card.classList.add("hover:border-blue-500");
      }
    });
  };

  /**
   * Saves the current order of card IDs to localStorage.
   */
  const saveCardOrder = () => {
    const cards = Array.from(dashboardGrid.children);
    const order = cards.map((card) => card.dataset.cardId);
    localStorage.setItem(CARD_ORDER_KEY, JSON.stringify(order));
  };

  /**
   * Loads the card order from localStorage and reorders the grid.
   */
  const loadCardOrder = () => {
    const savedOrder = JSON.parse(localStorage.getItem(CARD_ORDER_KEY));
    if (savedOrder) {
      const existingCards = {};
      // Map current cards by their ID for easy lookup
      Array.from(dashboardGrid.children).forEach((card) => {
        existingCards[card.dataset.cardId] = card;
      });

      // Clear the current grid
      dashboardGrid.innerHTML = "";

      // Append cards in the saved order
      savedOrder.forEach((cardId) => {
        if (existingCards[cardId]) {
          // Ensure the card actually exists
          dashboardGrid.appendChild(existingCards[cardId]);
        }
      });

      // Add any new cards that might not have been in the saved order (append at the end)
      Object.values(existingCards).forEach((card) => {
        if (!dashboardGrid.contains(card)) {
          dashboardGrid.appendChild(card);
        }
      });
    }
  };

  /**
   * Handles the dragstart event for a dashboard card.
   * @param {DragEvent} e - The drag event.
   */
  const handleDragStart = (e) => {
    if (dashboardGrid.dataset.locked === "true") {
      // Prevent dragging if locked
      e.preventDefault();
      return;
    }
    draggedItem = e.target;
    e.dataTransfer.effectAllowed = "move";
    // Optionally set a drag image
    // e.dataTransfer.setDragImage(e.target, 0, 0);
    setTimeout(() => {
      e.target.classList.add("opacity-50", "border-blue-500"); // Make dragged item semi-transparent
    }, 0);
  };

  /**
   * Handles the dragover event for a dashboard card or the grid container.
   * Allows dropping if not locked and target is a card or the grid itself.
   * @param {DragEvent} e - The drag event.
   */
  const handleDragOver = (e) => {
    e.preventDefault(); // Necessary to allow dropping
    if (dashboardGrid.dataset.locked === "true" || !draggedItem) return;

    const target = e.target.closest(".dashboard-card");
    if (target && target !== draggedItem) {
      // Determine if dragging before or after the target
      const rect = target.getBoundingClientRect();
      const offset = e.clientY - rect.top;
      const insertBefore = offset < rect.height / 2;

      if (insertBefore) {
        dashboardGrid.insertBefore(draggedItem, target);
      } else {
        dashboardGrid.insertBefore(draggedItem, target.nextSibling);
      }
    }
  };

  /**
   * Handles the drop event, finalizing the reorder and saving.
   * @param {DragEvent} e - The drag event.
   */
  const handleDrop = (e) => {
    e.preventDefault(); // Prevent default browser drop behavior (e.g., opening file)
    if (dashboardGrid.dataset.locked === "true" || !draggedItem) return;

    saveCardOrder(); // Save the new order
    draggedItem.classList.remove("opacity-50", "border-blue-500");
    draggedItem = null;
  };

  /**
   * Handles dragend event to clean up classes.
   * @param {DragEvent} e - The drag event.
   */
  const handleDragEnd = (e) => {
    e.target.classList.remove("opacity-50", "border-blue-500");
    draggedItem = null;
  };

  /**
   * Toggles the locked state of the dashboard layout.
   */
  const toggleLockedState = () => {
    const isLocked = dashboardGrid.dataset.locked === "true";
    dashboardGrid.dataset.locked = !isLocked; // Toggle the data attribute
    localStorage.setItem(LAYOUT_LOCKED_KEY, !isLocked); // Save preference

    // Update button text and icon
    if (!isLocked) {
      // Just became locked
      toggleLockButton.innerHTML =
        '<i class="fas fa-lock mr-2"></i> Lock Layout';
      toggleLockButton.classList.replace("bg-red-600", "bg-blue-600");
      toggleLockButton.classList.replace(
        "hover:bg-red-700",
        "hover:bg-blue-700",
      );
    } else {
      // Just became unlocked
      toggleLockButton.innerHTML =
        '<i class="fas fa-unlock mr-2"></i> Unlock Layout';
      toggleLockButton.classList.replace("bg-blue-600", "bg-red-600");
      toggleLockButton.classList.replace(
        "hover:bg-blue-700",
        "hover:bg-red-700",
      );
    }

    updateCardDraggableState(!isLocked); // Update draggable status of cards
  };

  // --- Event Listeners ---
  toggleLockButton.addEventListener("click", toggleLockedState);

  // Attach drag and drop listeners to the grid (event delegation)
  dashboardGrid.addEventListener("dragstart", (e) => {
    if (e.target.classList.contains("dashboard-card")) {
      handleDragStart(e);
    }
  });
  dashboardGrid.addEventListener("dragover", handleDragOver);
  dashboardGrid.addEventListener("drop", handleDrop);
  dashboardGrid.addEventListener("dragend", handleDragEnd); // Cleanup after drag

  // --- Initial Setup ---
  // Load locked state preference from localStorage
  const savedLockedState = localStorage.getItem(LAYOUT_LOCKED_KEY);
  if (savedLockedState !== null) {
    const isLayoutLocked = savedLockedState === "true";
    dashboardGrid.dataset.locked = isLayoutLocked;
    // Apply the correct button text/icon and card draggable state immediately
    if (isLayoutLocked) {
      toggleLockButton.innerHTML =
        '<i class="fas fa-lock mr-2"></i> Lock Layout';
      toggleLockButton.classList.replace("bg-red-600", "bg-blue-600");
      toggleLockButton.classList.replace(
        "hover:bg-red-700",
        "hover:bg-blue-700",
      );
    } else {
      toggleLockButton.innerHTML =
        '<i class="fas fa-unlock mr-2"></i> Unlock Layout';
      toggleLockButton.classList.replace("bg-blue-600", "bg-red-600");
      toggleLockButton.classList.replace(
        "hover:bg-blue-700",
        "hover:bg-red-700",
      );
    }
    updateCardDraggableState(isLayoutLocked);
  } else {
    // Default to locked if no preference saved
    dashboardGrid.dataset.locked = "true";
    updateCardDraggableState(true);
  }

  // Load card order after initial setup
  loadCardOrder();
});
