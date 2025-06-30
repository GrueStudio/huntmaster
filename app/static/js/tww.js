(function () {
  // Initialize all widgets on page
  const containers = document.querySelectorAll(".tww-container");

  containers.forEach((container) => {
    const selection = container.querySelector(".tww-selection");
    const label = container.querySelector(".tww-time-label");
    const track = container.querySelector(".tww-hour-track");

    const now = new Date();
    const startHour = now.getHours();
    const totalHours = 12;

    // Render hour blocks for this container
    track.innerHTML = "";
    for (let i = 0; i < totalHours; i++) {
      const hour = (startHour + i) % 24;
      const block = document.createElement("div");
      block.classList.add("tww-hour-block");
      const isAM = hour < 12;
      const shade = i % 2 === 0 ? "1" : "2";
      block.classList.add(`tww-${isAM ? "am" : "pm"}${shade}`);
      track.appendChild(block);
    }

    let containerWidth = container.offsetWidth;
    let hourWidth = containerWidth / totalHours;

    // Initial window values (start at 2h, end at 4h)
    let selStart = hourWidth * 2;
    let selEnd = hourWidth * 4;

    // Drag state
    let dragType = null; // 'move', 'resize-left', 'resize-right'
    let dragStartX = 0;
    let dragStartSelStart = 0;
    let dragStartSelEnd = 0;

    function updateDisplay() {
      selection.style.left = selStart + "px";
      selection.style.width = selEnd - selStart + "px";

      const startHourFloat = (selStart / containerWidth) * totalHours;
      const endHourFloat = (selEnd / containerWidth) * totalHours;

      const start = (startHour + Math.floor(startHourFloat)) % 24;
      const end = (startHour + Math.floor(endHourFloat)) % 24;

      const pad = (n) => n.toString().padStart(2, "0");
      label.textContent = `${pad(start)}:00 - ${pad(end)}:00`;

      // Optional: trigger a custom event on container for external listeners
      const event = new CustomEvent("tww-change", {
        detail: { start, end },
      });
      container.dispatchEvent(event);
    }

    function onMouseDown(e) {
      e.preventDefault();
      if (e.target.classList.contains("tww-resizer-left")) {
        dragType = "resize-left";
      } else if (e.target.classList.contains("tww-resizer-right")) {
        dragType = "resize-right";
      } else if (e.target === selection) {
        dragType = "move";
      } else {
        dragType = null;
      }
      if (dragType) {
        dragStartX = e.clientX;
        dragStartSelStart = selStart;
        dragStartSelEnd = selEnd;
        document.body.style.userSelect = "none";
      }
    }

    function onMouseMove(e) {
      if (!dragType) return;
      const dx = e.clientX - dragStartX;
      if (dragType === "move") {
        let newStart = Math.min(
          Math.max(dragStartSelStart + dx, 0),
          containerWidth - (selEnd - selStart),
        );
        selStart = newStart;
        selEnd = selStart + (dragStartSelEnd - dragStartSelStart);
      } else if (dragType === "resize-left") {
        let newStart = Math.min(
          Math.max(dragStartSelStart + dx, 0),
          selEnd - 40,
        );
        selStart = newStart;
      } else if (dragType === "resize-right") {
        let newEnd = Math.max(
          Math.min(dragStartSelEnd + dx, containerWidth),
          selStart + 40,
        );
        selEnd = newEnd;
      }
      updateDisplay();
    }

    function onMouseUp() {
      dragType = null;
      document.body.style.userSelect = "";
    }

    selection.addEventListener("mousedown", onMouseDown);
    container
      .querySelector(".tww-resizer-left")
      .addEventListener("mousedown", onMouseDown);
    container
      .querySelector(".tww-resizer-right")
      .addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    updateDisplay();

    // Expose value getters on container element
    container.twwValue = {
      get start() {
        return Math.floor((selStart / containerWidth) * totalHours);
      },
      get end() {
        return Math.floor((selEnd / containerWidth) * totalHours);
      },
    };
  });
})();
