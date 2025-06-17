// static/scp_vote.js

document.addEventListener("DOMContentLoaded", () => {
  const messageArea = document.getElementById("message-area");
  const errorArea = document.getElementById("error-area");

  function showMessage(message, type = "success") {
    if (type === "success") {
      messageArea.textContent = message;
      messageArea.classList.remove("hidden", "bg-red-500");
      messageArea.classList.add("bg-green-500");
      errorArea.classList.add("hidden");
    } else {
      // type === 'error'
      errorArea.textContent = message;
      errorArea.classList.remove("hidden", "bg-green-500");
      errorArea.classList.add("bg-red-500");
      messageArea.classList.add("hidden");
    }
    setTimeout(() => {
      messageArea.classList.add("hidden");
      errorArea.classList.add("hidden");
    }, 5000); // Hide after 5 seconds
  }

  document.querySelectorAll(".vote-button").forEach((button) => {
    button.addEventListener("click", async (event) => {
      const clickedButton = event.target.closest(".vote-button");
      const proposal = clickedButton.closest("[data-proposal-id]");
      const proposalId = proposal.dataset.proposalId;
      const voteType = clickedButton.dataset.voteType; // 'upvote' or 'downvote'
      const url = `/worlds/${window.location.pathname.split("/")[2]}/spawns/${window.location.pathname.split("/")[4]}/vote`;

      const formData = new FormData();
      formData.append("proposal_id", proposalId);
      formData.append("vote_type", voteType);

      const proposalDiv = event.target.closest("[data-proposal-id]");
      if (!proposalDiv) {
        console.error("Parent proposal div not found for clicked button.");
        showMessage(
          "An internal error occurred. Please refresh the page.",
          "error",
        );
        return;
      }

      const voteSection = proposalDiv.querySelector(".vote-section");
      if (!voteSection) {
        console.error(
          "Vote section not found within proposal div for ID:",
          proposalId,
        );
        showMessage(
          "An internal error occurred. Please refresh the page.",
          "error",
        );
        return;
      }

      // Get references to the specific upvote/downvote buttons within THIS vote section
      const upvoteButton = voteSection.querySelector(
        '.vote-button[data-vote-type="upvote"]',
      );
      const downvoteButton = voteSection.querySelector(
        '.vote-button[data-vote-type="downvote"]',
      );

      // Disable buttons immediately
      if (upvoteButton) {
        upvoteButton.disabled = true;
        upvoteButton.style.opacity = "0.7";
      }
      if (downvoteButton) {
        downvoteButton.disabled = true;
        downvoteButton.style.opacity = "0.7";
      }

      try {
        const response = await fetch(url, {
          method: "POST",
          body: formData,
        });

        const result = await response.json();

        if (response.ok) {
          showMessage(result.message, "success");

          // Generate static vote display HTML with updated counts
          let staticVoteHtml = `
                        <div class="flex items-center space-x-2 text-gray-400 font-bold text-sm">
                            Your Vote:
                            ${result.your_vote === "upvote" ? '<span class="text-green-400 text-lg">&#x1F44D;</span>' : ""}
                            ${result.your_vote === "downvote" ? '<span class="text-red-400 text-lg">&#x1F44E;</span>' : ""}
                            <span class="ml-auto">Total Votes: <span class="total-votes-count">${result.total_votes}</span></span>
                        </div>
                    `;
          // Replace the interactive section with the static display
          voteSection.innerHTML = staticVoteHtml;
        } else {
          // Handle HTTP errors
          const errorMessage =
            result.detail || result.message || "An unknown error occurred.";
          showMessage(errorMessage, "error");
          // Re-enable buttons on error
          if (upvoteButton) {
            upvoteButton.disabled = false;
            upvoteButton.style.opacity = "1";
          }
          if (downvoteButton) {
            downvoteButton.disabled = false;
            downvoteButton.style.opacity = "1";
          }
        }
      } catch (error) {
        console.error("Fetch error:", error);
        showMessage("Network error or server unreachable.", "error");
        // Re-enable buttons on network error
        if (upvoteButton) {
          upvoteButton.disabled = false;
          upvoteButton.style.opacity = "1";
        }
        if (downvoteButton) {
          downvoteButton.disabled = false;
          downvoteButton.style.opacity = "1";
        }
      }
    });
  });
});
