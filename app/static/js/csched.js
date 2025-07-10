// Updated ClaimScheduleWidget.js with date navigation support
class ClaimScheduleWidget {
  constructor(container, options = {}) {
    this.container = container;
    this.options = {
      lockingPeriodMinutes: 15,
      ...options,
    };

    this.currentTimeIndicator = null;
    this.tooltip = null;
    this.hourMarks = [];
    this.timeSlots = [];
    this.hunts = [];
    this.bids = [];
    this.users = {};

    // Add a property to track the current display date
    this.displayDate = new Date();

    // Calculate initial Tibia day start
    this.updateTibiaDayStart();

    this.lockingPeriodEnd = new Date();
    this.lockingPeriodEnd.setMinutes(
      this.lockingPeriodEnd.getMinutes() + this.options.lockingPeriodMinutes,
    );

    this.init();
    this.setupEventListeners();
  }

  // NEW METHOD: Update the Tibia day start for the current display date
  updateTibiaDayStart() {
    // Create a date for the display date at 10 AM Berlin time
    const displayDate = new Date(this.displayDate);
    const berlinTime10AM = new Date(
      displayDate.getFullYear(),
      displayDate.getMonth(),
      displayDate.getDate(),
      10,
      0,
      0,
      0,
    );

    // Convert Berlin time to UTC, then to local time
    const berlinOffset = this.getBerlinOffset(berlinTime10AM);
    const berlinTime10AMUTC = new Date(berlinTime10AM.getTime() - berlinOffset);

    // Convert UTC to local time
    const now = new Date();
    const localOffset = now.getTimezoneOffset() * 60000;
    this.tibiaDayStart = new Date(berlinTime10AMUTC.getTime() - localOffset);

    // For historical dates, we want the exact Tibia day start for that date
    // No need to adjust for "current time" when viewing other dates
  }

  // NEW METHOD: Set the display date and update the widget
  setDisplayDate(date) {
    this.displayDate = new Date(date);
    this.updateTibiaDayStart();
    this.renderHourMarks(); // Re-render hour marks for new date
    this.renderAllItems(); // Re-render all items
    this.updateCurrentTimeIndicator(); // Update time indicator
  }

  getBerlinOffset(date) {
    const year = date.getFullYear();
    const dstStart = this.getLastSunday(new Date(year, 2, 31));
    const dstEnd = this.getLastSunday(new Date(year, 9, 31));
    const isDST = date >= dstStart && date < dstEnd;
    return isDST ? 2 * 60 * 60 * 1000 : 1 * 60 * 60 * 1000;
  }

  getLastSunday(date) {
    const lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0);
    const lastSunday = new Date(lastDay);
    lastSunday.setDate(lastDay.getDate() - lastDay.getDay());
    lastSunday.setHours(2, 0, 0, 0);
    return lastSunday;
  }

  init() {
    this.container.innerHTML = `
      <div class="bsched-hourmarks"></div>
      <div class="csched-schedule">
        <div class="csched-sched-label">Schedule</div>
      </div>
      <div class="csched-my-bids">
        <div class="csched-user-label">
          <div class="user-avatar">Y</div>
          My Bids
        </div>
      </div>
      <div class="csched-other-bids-container"></div>
    `;

    this.tooltip = document.createElement("div");
    this.tooltip.className = "tooltip";
    this.tooltip.style.display = "none";
    document.body.appendChild(this.tooltip);

    this.renderHourMarks();
    this.updateCurrentTimeIndicator();

    setInterval(() => {
      this.updateCurrentTimeIndicator();
      this.updateLockingPeriod();
    }, 60000);
  }

  setupEventListeners() {
    window.addEventListener("resize", () => {
      this.renderAllItems();
    });
  }

  renderHourMarks() {
    const hourMarksContainer =
      this.container.querySelector(".bsched-hourmarks");
    hourMarksContainer.innerHTML = "";
    this.hourMarks = []; // Clear the array

    const label = document.createElement("div");
    label.className = "hour-mark-label";
    label.textContent = "Time";
    hourMarksContainer.appendChild(label);

    for (let i = 0; i <= 24; i++) {
      const hourTime = new Date(
        this.tibiaDayStart.getTime() + i * 60 * 60 * 1000,
      );
      const hour = hourTime.getHours();
      const hourMark = document.createElement("div");
      hourMark.className = "hour-mark";
      hourMark.textContent = `${hour}`;
      hourMark.dataset.hour = hour;

      const ssHour = i === 0 ? "SS+0" : `SS+${i}`;
      hourMark.title = `${hour}:00 (${ssHour})`;

      hourMarksContainer.appendChild(hourMark);
      this.hourMarks.push(hourMark);
    }

    // Re-create current time indicator
    if (this.currentTimeIndicator) {
      this.currentTimeIndicator.remove();
    }
    this.currentTimeIndicator = document.createElement("div");
    this.currentTimeIndicator.className = "current-time";
    hourMarksContainer.appendChild(this.currentTimeIndicator);
  }

  updateCurrentTimeIndicator() {
    if (!this.currentTimeIndicator) return;

    const now = new Date();
    const today = new Date();
    const displayDateStr = this.displayDate.toDateString();
    const todayStr = today.toDateString();

    // Only show the current time indicator if we're viewing today's schedule
    if (displayDateStr !== todayStr) {
      this.currentTimeIndicator.style.display = "none";
      return;
    }

    this.currentTimeIndicator.style.display = "block";

    const hoursElapsed = (now - this.tibiaDayStart) / (1000 * 60 * 60);
    const positionPercentage = (hoursElapsed / 24) * 100;
    const clampedPercentage = Math.max(0, Math.min(100, positionPercentage));

    const container = this.container;
    const containerWidth = container.offsetWidth;
    const labelColumnWidth = window.innerWidth <= 768 ? 80 : 120;
    const gridColumnsWidth = containerWidth - labelColumnWidth;
    const leftPixels = (clampedPercentage / 100) * gridColumnsWidth;

    this.currentTimeIndicator.style.left = `${labelColumnWidth + leftPixels}px`;
  }

  updateLockingPeriod() {
    const now = new Date();
    this.lockingPeriodEnd = new Date(
      now.getTime() + this.options.lockingPeriodMinutes * 60 * 1000,
    );
    this.renderAllItems();
  }

  parseUtcTime(utcTimeStr) {
    if (!utcTimeStr || typeof utcTimeStr !== "string") {
      console.error("Invalid UTC time string:", utcTimeStr);
      return null;
    }

    const utcDate = new Date(
      utcTimeStr + (utcTimeStr.includes("Z") ? "" : "Z"),
    );
    return new Date(utcDate.getTime());
  }

  truncateToDisplayWindow(start, end) {
    const displayStart = this.tibiaDayStart;
    const displayEnd = new Date(displayStart.getTime() + 24 * 60 * 60 * 1000);

    if (end < displayStart) return null;
    if (start > displayEnd) return null;

    const truncatedStart = start < displayStart ? displayStart : start;
    const truncatedEnd = end > displayEnd ? displayEnd : end;

    return {
      start: truncatedStart,
      end: truncatedEnd,
    };
  }

  addUser(userData) {
    if (!this.users[userData.id]) {
      this.users[userData.id] = userData;
    }
    return this.users[userData.id];
  }

  addTimeSlot(timeSlotData, bidData) {
    const localStart = this.parseUtcTime(timeSlotData.start);
    const localEnd = this.parseUtcTime(timeSlotData.end);

    const truncated = this.truncateToDisplayWindow(localStart, localEnd);
    if (!truncated) return;

    timeSlotData.localStart = truncated.start;
    timeSlotData.localEnd = truncated.end;
    timeSlotData.bid = bidData;
    bidData.status = "successful";

    this.timeSlots.push(timeSlotData);
    this.renderTimeSlot(timeSlotData);
  }

  addHunt(huntData, bidData) {
    const localStart = this.parseUtcTime(huntData.start);
    const localEnd = this.parseUtcTime(huntData.end);

    const truncated = this.truncateToDisplayWindow(localStart, localEnd);
    if (!truncated) return;

    huntData.localStart = truncated.start;
    huntData.localEnd = truncated.end;
    huntData.bid = bidData;
    bidData.status = "successful";

    this.hunts.push(huntData);
    this.renderHunt(huntData);
  }

  addBid(bidData, isCurrentUser = false) {
    const startTime = bidData.hunt_window_start || bidData.start;
    const endTime = bidData.hunt_window_end || bidData.end;

    if (!startTime || !endTime) {
      return;
    }

    const localStart = this.parseUtcTime(startTime);
    const localEnd = this.parseUtcTime(endTime);

    if (!localStart || !localEnd) {
      console.error("Failed to parse bid time data:", bidData);
      return;
    }

    const truncated = this.truncateToDisplayWindow(localStart, localEnd);
    if (!truncated) return;

    bidData.localStart = truncated.start;
    bidData.localEnd = truncated.end;
    bidData.isCurrentUser = isCurrentUser;

    const bidPoints = bidData.bid_points;
    const userId = bidData.user_id;
    const claimTime = bidData.claim_time;

    const claimDeadline = new Date(localEnd);
    claimDeadline.setSeconds(claimDeadline.getSeconds() - (claimTime || 0));

    if (!bidData.status) {
      const now = new Date();
      bidData.status = claimDeadline < now ? "failed" : "active";
    }

    this.bids.push(bidData);
    this.addUser({
      id: userId,
      name: bidData.userName || "Unknown User",
    });
    this.renderBid(bidData, isCurrentUser);
  }

  renderAllItems() {
    // Clear existing items
    const scheduleContainer = this.container.querySelector(".csched-schedule");
    const myBidsContainer = this.container.querySelector(".csched-my-bids");
    const otherBidsContainer = this.container.querySelector(
      ".csched-other-bids-container",
    );

    scheduleContainer
      .querySelectorAll(".hunt-item, .timeslot-item")
      .forEach((el) => el.remove());
    myBidsContainer
      .querySelectorAll(".bid-window")
      .forEach((el) => el.remove());
    otherBidsContainer.innerHTML = "";

    // Re-render all items
    this.timeSlots.forEach((ts) => this.renderTimeSlot(ts));
    this.hunts.forEach((h) => this.renderHunt(h));

    const sortedBids = [...this.bids].sort((a, b) => b.points - a.points);
    const userBids = sortedBids.filter((b) => b.isCurrentUser);

    if (userBids.length > 0) {
      myBidsContainer.style.display = "grid";
      userBids.forEach((b) => this.renderBid(b, true));
    } else {
      myBidsContainer.style.display = "none";
    }

    sortedBids
      .filter((b) => !b.isCurrentUser)
      .forEach((b) => this.renderBid(b, false));
  }

  renderTimeSlot(timeSlotData) {
    const scheduleContainer = this.container.querySelector(".csched-schedule");
    const timeSlotElement = document.createElement("div");
    timeSlotElement.className = "timeslot-item";
    timeSlotElement.dataset.id = timeSlotData.id;

    this.positionTimeItem(
      timeSlotElement,
      timeSlotData.localStart,
      timeSlotData.localEnd,
    );

    const bid = timeSlotData.bid;
    const avatar = document.createElement("div");
    avatar.className = "schedule-avatar";
    avatar.textContent = bid.userName.charAt(0).toUpperCase();
    timeSlotElement.appendChild(avatar);

    this.addTooltip(
      timeSlotElement,
      `Temporary Slot\nWinner: ${bid.userName}\nPoints: ${bid.points}\n${this.formatTimeRange(timeSlotData.localStart, timeSlotData.localEnd)}`,
    );

    scheduleContainer.appendChild(timeSlotElement);
  }

  renderHunt(huntData) {
    const scheduleContainer = this.container.querySelector(".csched-schedule");
    const huntElement = document.createElement("div");
    huntElement.className = "hunt-item";
    huntElement.dataset.id = huntData.id;

    this.positionTimeItem(huntElement, huntData.localStart, huntData.localEnd);

    const bid = huntData.bid;
    const avatar = document.createElement("div");
    avatar.className = "schedule-avatar";
    avatar.textContent = bid.userName.charAt(0).toUpperCase();
    huntElement.appendChild(avatar);

    this.addTooltip(
      huntElement,
      `Confirmed Hunt\nWinner: ${bid.userName}\nPoints: ${bid.points}\n${this.formatTimeRange(huntData.localStart, huntData.localEnd)}`,
    );

    scheduleContainer.appendChild(huntElement);
  }

  renderBid(bidData, isCurrentUser = false) {
    const container = isCurrentUser
      ? this.container.querySelector(".csched-my-bids")
      : this.createUserBidContainer(
          bidData.user_id,
          bidData.userName || "Unknown User",
        );

    const bidElement = document.createElement("div");
    bidElement.className = `bid-window ${bidData.status}`;
    bidElement.dataset.id = bidData.id;

    this.positionTimeItem(bidElement, bidData.localStart, bidData.localEnd);
    bidElement.textContent = `${bidData.bid_points} pts`;

    const statusText =
      bidData.status === "successful"
        ? "Successful"
        : bidData.status === "failed"
          ? "Failed"
          : "Active";
    this.addTooltip(
      bidElement,
      `${bidData.userName || "Unknown User"}\nPoints: ${bidData.bid_points}\nStatus: ${statusText}\n${this.formatTimeRange(bidData.localStart, bidData.localEnd)}`,
    );

    container.appendChild(bidElement);
  }

  createUserBidContainer(userId, userName) {
    const otherBidsContainer = this.container.querySelector(
      ".csched-other-bids-container",
    );
    const user = this.users[userId] || {
      id: userId,
      name: userName || "Unknown User",
    };

    let userContainer = otherBidsContainer.querySelector(
      `.csched-user-bids[data-user-id="${userId}"]`,
    );

    if (!userContainer) {
      userContainer = document.createElement("div");
      userContainer.className = "csched-user-bids";
      userContainer.dataset.userId = userId;

      const userLabel = document.createElement("div");
      userLabel.className = "csched-user-label";

      const avatar = document.createElement("div");
      avatar.className = "user-avatar";
      avatar.textContent = (user.name || "U").charAt(0).toUpperCase();

      const usernameSpan = document.createElement("span");
      usernameSpan.className = "username-text";
      usernameSpan.textContent = user.name || "Unknown User";
      usernameSpan.title = user.name || "Unknown User";

      userLabel.appendChild(avatar);
      userLabel.appendChild(usernameSpan);
      userContainer.appendChild(userLabel);
      otherBidsContainer.appendChild(userContainer);
    }

    return userContainer;
  }

  positionTimeItem(element, startDate, endDate) {
    const startHours = (startDate - this.tibiaDayStart) / (1000 * 60 * 60);
    const endHours = (endDate - this.tibiaDayStart) / (1000 * 60 * 60);

    const totalHours = 24;
    const leftPercentage = (startHours / totalHours) * 100;
    const widthPercentage = ((endHours - startHours) / totalHours) * 100;

    const container = this.container;
    const containerWidth = container.offsetWidth;
    const labelColumnWidth = window.innerWidth <= 768 ? 80 : 120;
    const gridColumnsWidth = containerWidth - labelColumnWidth;

    const leftPixels = (leftPercentage / 100) * gridColumnsWidth;
    const widthPixels = (widthPercentage / 100) * gridColumnsWidth;

    element.style.left = `${labelColumnWidth + leftPixels}px`;
    element.style.width = `${widthPixels}px`;
  }

  addTooltip(element, content) {
    element.addEventListener("mouseenter", (e) => {
      this.tooltip.textContent = content;
      this.tooltip.style.display = "block";
      this.positionTooltip(e);
    });

    element.addEventListener("mousemove", (e) => {
      this.positionTooltip(e);
    });

    element.addEventListener("mouseleave", () => {
      this.tooltip.style.display = "none";
    });
  }

  positionTooltip(event) {
    const x = event.clientX;
    const y = event.clientY;
    const tooltipWidth = this.tooltip.offsetWidth;
    const tooltipHeight = this.tooltip.offsetHeight;
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;

    let left = x + 10;
    let top = y + 10;

    if (left + tooltipWidth > windowWidth) {
      left = x - tooltipWidth - 10;
    }

    if (top + tooltipHeight > windowHeight) {
      top = y - tooltipHeight - 10;
    }

    this.tooltip.style.left = `${left}px`;
    this.tooltip.style.top = `${top}px`;
  }

  formatTimeRange(startDate, endDate) {
    const startStr = startDate.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    const endStr = endDate.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    return `${startStr} - ${endStr}`;
  }

  clear() {
    this.timeSlots = [];
    this.hunts = [];
    this.bids = [];
    this.users = {};

    const myBidsContainer = this.container.querySelector(".csched-my-bids");
    myBidsContainer.style.display = "none";

    this.renderAllItems();
  }

  loadData(data) {
    this.clear();

    const usersMap = {};
    if (data.users) {
      data.users.forEach((user) => {
        usersMap[user.id] = user;
      });
    }

    if (data.bids && Array.isArray(data.bids)) {
      data.bids.forEach((b) => {
        const user = usersMap[b.user_id];
        if (user) {
          b.userName = user.username;
        }
        b.points = b.bid_points;
        this.addBid(b, b.isCurrentUser || false);
      });
    }

    if (data.timeslots) {
      data.timeslots.forEach((ts) => {
        const bid = data.bids.find((b) => b.id === ts.bidId);
        if (bid) this.addTimeSlot(ts, bid);
      });
    }

    if (data.hunts) {
      data.hunts.forEach((h) => {
        const bid = data.bids.find((b) => b.id === h.bidId);
        if (bid) this.addHunt(h, bid);
      });
    }
  }
}
