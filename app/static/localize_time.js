// static/localize_time.js

/**
 * Converts a UTC datetime string (ISO 8601 format, e.g., "2025-05-23T14:52:08Z")
 * to a localized string based on the user's browser settings.
 * @param {string} utcTimeString - The UTC datetime string to localize.
 * @returns {string} The localized datetime string.
 */
function localizeUtcToUserTime(utcTimeString) {
  // Create a Date object from the UTC ISO string (ending with 'Z' for UTC)
  const utcDate = new Date(utcTimeString);

  // Format to a user-friendly local string based on their locale
  // Options can be customized further for format (e.g., dateStyle, timeStyle)
  return utcDate.toLocaleString(navigator.language, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false, // Use 24-hour format; change to true for AM/PM
  });
}

/**
 * Converts a local datetime string (e.g., from <input type="datetime-local">)
 * to a UTC ISO 8601 string (e.g., "2025-05-23T19:00:00Z").
 * This is useful for sending local user input to a backend that expects UTC.
 * @param {string} localDatetimeString - The local datetime string (e.g., "YYYY-MM-DDTHH:MM").
 * @returns {string|null} The UTC ISO 8601 string with 'Z' suffix, or null if input is invalid.
 */
function convertLocalToUtcIso(localDatetimeString) {
  if (!localDatetimeString) {
    return null;
  }
  // Create a Date object from the local datetime string.
  // JavaScript's Date constructor will interpret this in the local timezone.
  const localDate = new Date(localDatetimeString);

  // Check if the date is valid
  if (isNaN(localDate.getTime())) {
    console.error(
      "Invalid local datetime string provided:",
      localDatetimeString,
    );
    return null;
  }

  // Convert the local Date object to a UTC ISO string.
  // toISOString() always returns a UTC string with 'Z' suffix.
  return localDate.toISOString();
}

// This part runs when the DOM is fully loaded
document.addEventListener("DOMContentLoaded", () => {
  // Find all span elements with the class 'local-datetime' and convert their times for display
  document.querySelectorAll("span.local-datetime").forEach((spanElement) => {
    const utcTime = spanElement.getAttribute("data-utc-time");
    if (utcTime) {
      spanElement.textContent = localizeUtcToUserTime(utcTime);
    }
  });

  // Example of how to use convertLocalToUtcIso for form submissions:
  // This is a conceptual example. You would attach this logic to your actual forms.
  // Imagine you have an input like: <input type="datetime-local" id="myLocalTimeInput">
  // And a form like: <form id="myForm">...</form>

  // const myForm = document.getElementById('myForm');
  // if (myForm) {
  //     myForm.addEventListener('submit', (event) => {
  //         const localTimeInput = document.getElementById('myLocalTimeInput');
  //         if (localTimeInput && localTimeInput.value) {
  //             const utcIsoString = convertLocalToUtcIso(localTimeInput.value);
  //             if (utcIsoString) {
  //                 // Create a hidden input field to send the UTC time to the backend
  //                 const hiddenInput = document.createElement('input');
  //                 hiddenInput.type = 'hidden';
  //                 hiddenInput.name = 'utc_time_for_backend'; // Name your backend expects
  //                 hiddenInput.value = utcIsoString;
  //                 myForm.appendChild(hiddenInput);
  //             } else {
  //                 // Handle invalid date input, e.g., prevent form submission
  //                 event.preventDefault();
  //                 alert('Please enter a valid date and time.');
  //             }
  //         }
  //     });
  // }
});
