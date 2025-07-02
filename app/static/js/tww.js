(function () {
  // Global variables to hold external settings for the TWW widget.
  let externalMinSelectionWidthPx = 0; // Minimum selection width in pixels.
  let externalMinDurationMinutes = 0; // Minimum duration in minutes.

  // Expose a global function for the main script to set the minimum width.
  window.setTwwMinSelectionWidth = function (widthPx) {
    externalMinSelectionWidthPx = widthPx;
    // Trigger an update on all TWW instances to apply the new min width immediately.
    document.querySelectorAll(".tww-container").forEach((container) => {
      if (container._twwInstance) {
        container._twwInstance.updateDisplay();
      }
    });
  };

  // Expose a global function to set the minimum duration in minutes.
  window.setTwwMinDurationMinutes = function (minutes) {
    externalMinDurationMinutes = minutes;
    // Trigger an update on all TWW instances to re-evaluate validity.
    document.querySelectorAll(".tww-container").forEach((container) => {
      if (container._twwInstance) {
        container._twwInstance.updateDisplay();
      }
    });
  };

  // Initialize all widgets on the page.
  const containers = document.querySelectorAll(".tww-container");

  containers.forEach((container) => {
    const selection = container.querySelector(".tww-selection");
    const label = container.querySelector(".tww-time-label");
    const track = container.querySelector(".tww-hour-track");

    // Create the "now" indicator bar
    const nowIndicator = document.createElement("div");
    nowIndicator.classList.add("tww-now-indicator");
    container.appendChild(nowIndicator);

    const now = new Date();
    const initialLoadHour = now.getHours(); // Store the hour when the widget was first loaded.
    const totalHours = 13; // Changed to 13 hours as requested.

    // Render hour blocks for this container.
    track.innerHTML = "";
    for (let i = 0; i < totalHours; i++) {
      const hour = (initialLoadHour + i) % 24; // Calculate the absolute hour for shading.
      const block = document.createElement("div");
      block.classList.add("tww-hour-block");
      const isAM = hour < 12;
      const shade = i % 2 === 0 ? "1" : "2"; // Alternating shades for visual distinction.
      block.classList.add(`tww-${isAM ? "am" : "pm"}${shade}`);
      track.appendChild(block);
    }

    let containerWidth = container.offsetWidth; // Current pixel width of the widget container.
    let hourWidth = containerWidth / totalHours; // Pixel width representing one hour on the track.

    // Initial window values (default to a 2-hour window starting 2 hours from the track's start).
    let selStart = hourWidth * 2;
    let selEnd = hourWidth * 4;

    // Drag state variables.
    let dragType = null; // 'move', 'resize-left', 'resize-right', 'new-selection'
    let dragStartX = 0; // Mouse X position when drag started.
    let dragStartSelStart = 0; // Selection's left position when drag started.
    let dragStartSelEnd = 0; // Selection's right position when drag started.

    /**
     * Updates the visual display of the selection window and its time label.
     * Also dispatches a custom event with the current selection details.
     */
    function updateDisplay() {
      selection.style.left = selStart + "px";
      selection.style.width = selEnd - selStart + "px";

      // Calculate the absolute Date objects for start and end times.
      // These getters are defined below in container.twwValue.
      const absoluteStartDate = container.twwValue.start;
      const absoluteEndDate = container.twwValue.end;
      const currentDurationMinutes = container.twwValue.durationMinutes;

      // Format the Date objects for the label text.
      const pad = (n) => n.toString().padStart(2, "0");
      const displayStartAbsolute = `${pad(absoluteStartDate.getHours())}:${pad(absoluteStartDate.getMinutes())}`;
      const displayEndAbsolute = `${pad(absoluteEndDate.getHours())}:${pad(absoluteEndDate.getMinutes())}`;

      label.textContent = `${displayStartAbsolute} - ${displayEndAbsolute}`;

      // --- Minimum Duration Validation ---
      if (currentDurationMinutes < externalMinDurationMinutes) {
        selection.classList.add("tww-invalid-selection");
        container.setAttribute("data-tww-valid", "false"); // Set attribute for form validation
      } else {
        selection.classList.remove("tww-invalid-selection");
        container.setAttribute("data-tww-valid", "true"); // Set attribute for form validation
      }

      // Dispatch a custom event to notify external scripts of changes.
      const event = new CustomEvent("tww-change", {
        detail: {
          start: absoluteStartDate, // Return Date object
          end: absoluteEndDate, // Return Date object
          startAbsolute: displayStartAbsolute,
          endAbsolute: displayEndAbsolute,
          durationMinutes: currentDurationMinutes,
          isValid: currentDurationMinutes >= externalMinDurationMinutes,
        },
      });
      container.dispatchEvent(event);
    }

    /**
     * Calculates the pixel position of a given Date object on the timeline.
     * @param {Date} date - The Date object to position.
     * @returns {number} The pixel position from the left of the container.
     */
    function getPixelPositionFromDate(date) {
      // Reference point for pixel calculation is the start of the current hour displayed on the track.
      const trackStartTime = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate(),
        initialLoadHour,
        0,
        0,
      );
      const diffMs = date.getTime() - trackStartTime.getTime();
      const totalMsOnTrack = totalHours * 60 * 60 * 1000; // Total milliseconds represented by the track
      return (diffMs / totalMsOnTrack) * containerWidth;
    }

    /**
     * Animates the "now" indicator bar and checks for hourly rollover.
     */
    function animateNowIndicator() {
      const currentNow = new Date(); // Get current time
      const nowPx = getPixelPositionFromDate(currentNow);

      // Check for hourly rollover
      if (currentNow.getHours() !== initialLoadHour) {
        // If the hour has changed since the widget loaded, refresh the page.
        window.location.reload();
        return; // Stop further animation frames as page will reload.
      }

      // Hide if "now" is outside the 13-hour window
      if (nowPx < 0 || nowPx > containerWidth) {
        nowIndicator.style.display = "none";
      } else {
        nowIndicator.style.display = "block";
        nowIndicator.style.left = nowPx + "px";
      }
      requestAnimationFrame(animateNowIndicator);
    }
    animateNowIndicator(); // Start the animation loop

    /**
     * Handles the mouse down event for starting a drag or resize operation.
     * @param {MouseEvent} e - The mouse event.
     */
    function onMouseDown(e) {
      e.preventDefault();
      if (e.target.classList.contains("tww-resizer-left")) {
        dragType = "resize-left";
      } else if (e.target.classList.contains("tww-resizer-right")) {
        dragType = "resize-right";
      } else if (e.target === selection) {
        dragType = "move";
      } else {
        // If clicking on the track background, initiate a new selection.
        dragType = "new-selection";
        const clickX = e.clientX - container.getBoundingClientRect().left;

        // Ensure new selection starts at or after "now"
        const nowPx = getPixelPositionFromDate(new Date());
        selStart = Math.max(nowPx, clickX);

        // Set end based on new start and min duration
        selEnd = selStart + (externalMinSelectionWidthPx || 40); // Use external min width, fallback to 40px.

        // Ensure new selection doesn't go out of bounds or past 12 hours from now
        const maxAllowedEndDateTime = new Date(
          Date.now() + 12 * 60 * 60 * 1000,
        ); // 12 hours from current moment
        const maxAllowedEndPx = getPixelPositionFromDate(maxAllowedEndDateTime);

        selEnd = Math.min(selEnd, maxAllowedEndPx, containerWidth);

        // If after constraining, the selection is too small, adjust start
        if (selEnd - selStart < (externalMinSelectionWidthPx || 40)) {
          selStart = selEnd - (externalMinSelectionWidthPx || 40);
          if (selStart < nowPx) selStart = nowPx; // Ensure it still doesn't go before now
        }
      }
      if (dragType) {
        dragStartX = e.clientX;
        dragStartSelStart = selStart;
        dragStartSelEnd = selEnd;
        document.body.style.userSelect = "none"; // Prevent text selection during drag.
      }
      updateDisplay(); // Update immediately for new selection or initial state.
    }

    /**
     * Handles the mouse move event for dragging or resizing the selection.
     * @param {MouseEvent} e - The mouse event.
     */
    function onMouseMove(e) {
      if (!dragType) return; // Only proceed if a drag/resize operation is active.

      const dx = e.clientX - dragStartX; // Change in X position since drag started.
      const minWidthPx = externalMinSelectionWidthPx || 40; // Use external min width, fallback to 40px.
      const nowPx = getPixelPositionFromDate(new Date()); // Current "now" position

      // Calculate the maximum allowed end pixel based on 12 hours from now
      const maxAllowedEndDateTime = new Date(Date.now() + 12 * 60 * 60 * 1000);
      const maxAllowedEndPx = getPixelPositionFromDate(maxAllowedEndDateTime);

      if (dragType === "move") {
        // Calculate new start position, ensuring it stays within container bounds
        // AND does not go before the "now" indicator.
        let newStart = Math.min(
          Math.max(dragStartSelStart + dx, nowPx), // Cannot go before 'now'
          containerWidth - (selEnd - selStart),
        );
        selStart = newStart;
        selEnd = selStart + (dragStartSelEnd - dragStartSelStart); // Maintain original width.

        // After moving, ensure the end doesn't exceed the 12-hour limit
        if (selEnd > maxAllowedEndPx) {
          selEnd = maxAllowedEndPx;
          selStart = selEnd - (dragStartSelEnd - dragStartSelStart); // Adjust start to maintain width
          if (selStart < nowPx) selStart = nowPx; // Ensure it still doesn't go before now
        }
      } else if (dragType === "resize-left") {
        // Calculate new left position, ensuring it doesn't go past the right handle
        // or the container's left edge, respects minimum width, AND does not go before "now".
        let newStart = Math.min(
          Math.max(dragStartSelStart + dx, nowPx), // Cannot go before 'now'
          selEnd - minWidthPx,
        );
        selStart = newStart;
      } else if (dragType === "resize-right") {
        // Calculate new right position, ensuring it doesn't go past the container's
        // right edge or the left handle, respects minimum width, AND does not go past maxAllowedEndPx.
        let newEnd = Math.max(
          Math.min(dragStartSelEnd + dx, containerWidth, maxAllowedEndPx), // Constrain by maxAllowedEndPx
          selStart + minWidthPx,
        );
        selEnd = newEnd;
      } else if (dragType === "new-selection") {
        // For a new selection initiated by dragging on the background.
        // The user is effectively setting the right edge of the new window.
        let currentXRelativeToContainer =
          e.clientX - container.getBoundingClientRect().left;
        let newSelEnd = Math.max(
          selStart + minWidthPx,
          Math.min(
            currentXRelativeToContainer,
            containerWidth,
            maxAllowedEndPx,
          ),
        ); // Constrain by maxAllowedEndPx
        selEnd = newSelEnd;
      }
      updateDisplay(); // Update the display after position changes.
    }

    /**
     * Handles the mouse up event, ending any drag or resize operation.
     */
    function onMouseUp() {
      dragType = null; // Reset drag type.
      document.body.style.userSelect = ""; // Re-enable text selection.
    }

    // Attach event listeners.
    selection.addEventListener("mousedown", onMouseDown);
    container
      .querySelector(".tww-resizer-left")
      .addEventListener("mousedown", onMouseDown);
    container
      .querySelector(".tww-resizer-right")
      .addEventListener("mousedown", onMouseDown);
    track.addEventListener("mousedown", onMouseDown); // Listen on the track for new selections.

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    // Expose value getters on the container element for external access.
    // These getters now return Date objects.
    container.twwValue = {
      get start() {
        const startPixelOffset = selStart;
        // Calculate total minutes offset from the start of the current day (00:00:00)
        // This makes the Date object absolute from the start of the day.
        const totalMinutesOffsetFromDayStart =
          (startPixelOffset / containerWidth) * totalHours * 60 +
          initialLoadHour * 60;

        // Create a Date object representing the absolute time.
        const absoluteDate = new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
          0,
          0,
          0,
          0,
        );
        absoluteDate.setMinutes(totalMinutesOffsetFromDayStart);

        return absoluteDate; // Return the Date object.
      },
      get end() {
        const endPixelOffset = selEnd;
        const totalMinutesOffsetFromDayStart =
          (endPixelOffset / containerWidth) * totalHours * 60 +
          initialLoadHour * 60;

        const absoluteDate = new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
          0,
          0,
          0,
          0,
        );
        absoluteDate.setMinutes(totalMinutesOffsetFromDayStart);

        return absoluteDate; // Return the Date object.
      },
      get durationMinutes() {
        // Calculate duration directly from the Date objects returned by the getters.
        const startMs = this.start.getTime(); // Use 'this' to call the getter.
        const endMs = this.end.getTime(); // Use 'this' to call the getter.
        return Math.round((endMs - startMs) / (1000 * 60));
      },
      // Expose validity state
      get isValid() {
        return this.durationMinutes >= externalMinDurationMinutes;
      },
    };

    updateDisplay(); // Initial display update when the widget is first set up.

    // Store an internal instance reference for external functions (like setTwwMinSelectionWidth)
    // to be able to trigger updates on specific widget instances.
    container._twwInstance = { updateDisplay: updateDisplay };

    // Add a ResizeObserver to update containerWidth if the widget's size changes (e.g., window resize).
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        if (entry.target === container) {
          containerWidth = container.offsetWidth;
          hourWidth = containerWidth / totalHours;
          updateDisplay(); // Re-render to adapt to the new size.
        }
      }
    });
    resizeObserver.observe(container);
  });
})();
