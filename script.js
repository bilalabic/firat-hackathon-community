/* Fırat Hackathon Community — etkinlik listesi (vanilla JS, bağımlılık yok) */

(function () {
  "use strict";

  var STATUS = {
    open: { label: "Başvurular Açık", cls: "status-open", order: 0 },
    upcoming: { label: "Yaklaşan", cls: "status-upcoming", order: 1 },
    ended: { label: "Sona Eren", cls: "status-ended", order: 2 }
  };

  var DAY = 86400000;

  var dateFormatter = new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric"
  });

  var els = {
    search: document.getElementById("search"),
    clear: document.getElementById("search-clear"),
    filters: document.getElementById("filters"),
    count: document.getElementById("result-count"),
    state: document.getElementById("state"),
    list: document.getElementById("events")
  };

  var allEvents = [];
  var activeFilter = "all";
  var query = "";

  /* ---------- tarih yardımcıları ---------- */

  // "YYYY-MM-DD" -> local takvim günü (UTC kayması olmadan)
  function parseLocalDate(value) {
    if (typeof value !== "string") return null;
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    var date = new Date(y, mo - 1, d);
    if (date.getFullYear() !== y || date.getMonth() !== mo - 1 || date.getDate() !== d) return null;
    return date;
  }

  function today() {
    var now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  function daysBetween(from, to) {
    return Math.round((to.getTime() - from.getTime()) / DAY);
  }

  function formatDate(date) {
    return date ? dateFormatter.format(date) : "";
  }

  /* ---------- durum ---------- */

  function computeStatus(event, now) {
    var deadline = event._deadline;
    var eventDate = event._eventDate;

    if (deadline && now.getTime() <= deadline.getTime()) return "open";
    if (eventDate && now.getTime() <= eventDate.getTime()) return "upcoming";
    if (!deadline && !eventDate) return "upcoming";
    return "ended";
  }

  // 3 gün veya daha az kaldıysa uyarı metni ("Son gün" / "Son 2 gün" / "Son 3 gün")
  function countdownLabel(event, now) {
    if (event._status !== "open" || !event._deadline) return "";
    var remaining = daysBetween(now, event._deadline) + 1; // bugün dahil
    if (remaining > 3 || remaining < 1) return "";
    return remaining === 1 ? "Son gün" : "Son " + remaining + " gün";
  }

  /* ---------- normalize / arama ---------- */

  var TR_MAP = { "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c", "â": "a", "î": "i", "û": "u" };

  function normalize(value) {
    if (!value) return "";
    return String(value)
      .replace(/[ıİşŞğĞüÜöÖçÇâîû]/g, function (ch) { return TR_MAP[ch] || ch; })
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "");
  }

  function matchesQuery(event, q) {
    if (!q) return true;
    return event._haystack.indexOf(q) !== -1;
  }

  /* ---------- hazırlama & sıralama ---------- */

  function prepare(list, now) {
    var prepared = [];
    for (var i = 0; i < list.length; i++) {
      var raw = list[i];
      if (!raw || typeof raw !== "object" || !raw.name) continue;

      var event = {
        id: String(raw.id || ""),
        name: String(raw.name),
        organizer: raw.organizer ? String(raw.organizer) : "",
        location: raw.location ? String(raw.location) : "",
        format: raw.format ? String(raw.format) : "",
        teamSize: raw.teamSize ? String(raw.teamSize) : "",
        description: raw.description ? String(raw.description) : "",
        url: safeUrl(raw.url)
      };

      event._deadline = parseLocalDate(raw.deadline);
      event._eventDate = parseLocalDate(raw.eventDate);
      event._status = computeStatus(event, now);
      event._countdown = countdownLabel(event, now);
      event._haystack = normalize([event.name, event.organizer, event.location, event.description].join(" "));

      prepared.push(event);
    }
    return prepared.sort(function (a, b) { return compare(a, b, now); });
  }

  function compare(a, b, now) {
    var byStatus = STATUS[a._status].order - STATUS[b._status].order;
    if (byStatus !== 0) return byStatus;

    if (a._status === "open") {
      // en yakın son başvuru tarihi önce
      return time(a._deadline, Infinity) - time(b._deadline, Infinity);
    }
    if (a._status === "upcoming") {
      // en yakın etkinlik tarihi önce
      return time(a._eventDate, Infinity) - time(b._eventDate, Infinity);
    }
    // sona erenlerde en yakın geçmiş etkinlik önce
    return time(b._eventDate, -Infinity) - time(a._eventDate, -Infinity);
  }

  function time(date, fallback) {
    return date ? date.getTime() : fallback;
  }

  // Yalnızca http/https bağlantılara izin ver (javascript: vb. engellenir)
  function safeUrl(value) {
    if (typeof value !== "string") return "";
    var trimmed = value.trim();
    if (!/^https?:\/\//i.test(trimmed)) return "";
    try {
      var parsed = new URL(trimmed);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
      return parsed.href;
    } catch (err) {
      return "";
    }
  }

  /* ---------- DOM yardımcıları ---------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null && text !== "") node.textContent = text;
    return node;
  }

  function buildCard(event) {
    var card = el("article", "card");

    var top = el("div", "card-top");
    var status = el("span", "status " + STATUS[event._status].cls);
    status.appendChild(el("span", "status-dot"));
    status.appendChild(el("span", null, STATUS[event._status].label));
    top.appendChild(status);
    if (event._countdown) top.appendChild(el("span", "countdown", event._countdown));
    card.appendChild(top);

    var head = el("div");
    var title = el("h2", "card-title", event.name);
    head.appendChild(title);
    if (event.organizer) head.appendChild(el("p", "card-organizer", event.organizer));
    card.appendChild(head);

    if (event._deadline || event._eventDate) {
      var dates = el("div", "dates");
      dates.appendChild(dateBlock("Son Başvuru", event._deadline));
      dates.appendChild(dateBlock("Etkinlik Tarihi", event._eventDate));
      card.appendChild(dates);
    }

    var meta = [event.location, event.format, event.teamSize].filter(Boolean);
    if (meta.length) card.appendChild(el("p", "meta", meta.join(" · ")));

    if (event.description) card.appendChild(el("p", "description", event.description));

    if (event.url) {
      var link = el("a", "card-link");
      link.href = event.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.appendChild(document.createTextNode("Başvuru ve Detaylar"));
      link.appendChild(el("span", "arrow", "→"));
      var sr = el("span", "visually-hidden", " (" + event.name + ", yeni sekmede açılır)");
      link.appendChild(sr);
      card.appendChild(link);
    }

    return card;
  }

  function dateBlock(label, date) {
    var wrap = el("div");
    wrap.appendChild(el("span", "date-label", label));
    wrap.appendChild(el("p", "date-value", date ? formatDate(date) : "—"));
    return wrap;
  }

  /* ---------- render ---------- */

  function showState(message, withRetry) {
    els.list.replaceChildren();
    els.state.replaceChildren();
    els.state.hidden = false;
    els.state.appendChild(document.createTextNode(message));
    if (withRetry) {
      var retry = el("button", "state-retry", "Tekrar dene");
      retry.type = "button";
      retry.addEventListener("click", load);
      els.state.appendChild(document.createElement("br"));
      els.state.appendChild(retry);
    }
  }

  function updateCounts() {
    var counts = { all: allEvents.length, open: 0, upcoming: 0, ended: 0 };
    for (var i = 0; i < allEvents.length; i++) counts[allEvents[i]._status]++;

    var nodes = document.querySelectorAll("[data-count]");
    for (var j = 0; j < nodes.length; j++) {
      nodes[j].textContent = counts[nodes[j].getAttribute("data-count")];
    }
  }

  function render() {
    var q = normalize(query.trim());
    var visible = allEvents.filter(function (event) {
      if (activeFilter !== "all" && event._status !== activeFilter) return false;
      return matchesQuery(event, q);
    });

    els.count.textContent = visible.length + " etkinlik";

    if (!allEvents.length) {
      showState("Henüz listelenen bir etkinlik yok.", false);
      els.count.textContent = "";
      return;
    }

    if (!visible.length) {
      showState(q ? "Aramanızla eşleşen etkinlik bulunamadı." : "Bu filtreye uyan etkinlik bulunamadı.", false);
      return;
    }

    els.state.hidden = true;
    var frag = document.createDocumentFragment();
    for (var i = 0; i < visible.length; i++) frag.appendChild(buildCard(visible[i]));
    els.list.replaceChildren(frag);
  }

  /* ---------- olaylar ---------- */

  els.search.addEventListener("input", function () {
    query = els.search.value;
    els.clear.hidden = query === "";
    render();
  });

  els.clear.addEventListener("click", function () {
    els.search.value = "";
    query = "";
    els.clear.hidden = true;
    els.search.focus();
    render();
  });

  els.filters.addEventListener("click", function (evt) {
    var chip = evt.target.closest(".chip");
    if (!chip) return;
    activeFilter = chip.getAttribute("data-filter");
    var chips = els.filters.querySelectorAll(".chip");
    for (var i = 0; i < chips.length; i++) {
      chips[i].setAttribute("aria-pressed", chips[i] === chip ? "true" : "false");
    }
    render();
  });

  /* ---------- yükleme ---------- */

  function load() {
    showState("Etkinlikler yükleniyor…", false);
    fetch("./events.json", { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!Array.isArray(data)) throw new Error("Geçersiz veri");
        allEvents = prepare(data, today());
        updateCounts();
        render();
      })
      .catch(function () {
        allEvents = [];
        updateCounts();
        els.count.textContent = "";
        showState("Etkinlikler yüklenemedi. Lütfen tekrar deneyin.", true);
      });
  }

  load();
})();
