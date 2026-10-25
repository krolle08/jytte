// Home Hub client behaviour, FEAT-002 (hand-over section 7.5).
// Everything else is server-rendered and swapped by htmx.
(function () {
  // Theme: the server renders the class from the cookie; this flips it
  // and records the choice. The POST carries HX-Request, which the
  // server requires on every action (its CSRF guard).
  function setTheme(t) {
    var s = document.getElementById("shell");
    if (s) s.classList.toggle("lt", t === "light");
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("#theme-btn");
    if (t) {
      var s = document.getElementById("shell");
      var light = !s.classList.contains("lt");
      setTheme(light ? "light" : "dark");
      fetch("/act/theme", {
        method: "POST", headers: { "HX-Request": "true" },
        body: new URLSearchParams({ theme: light ? "light" : "dark" }),
      });
    }
    var c = e.target.closest("[data-copy]");
    if (c) {
      var o = c.textContent;
      var done = function () { c.textContent = "Copied"; setTimeout(function () { c.textContent = o; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(c.dataset.copy).then(done, function () { c.textContent = "Copy blocked"; });
    }
    // A maintenance menu closes when you click anywhere else.
    document.querySelectorAll("details.mmenu[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  // The Settings row answers with HX-Trigger {"hh:theme": "light"}.
  document.addEventListener("hh:theme", function (e) { setTheme(e.detail && e.detail.value); });

  // A second click on a row's link collapses its panel instead of
  // fetching it again.
  document.addEventListener("htmx:beforeRequest", function (e) {
    var el = e.detail.elt;
    if (!el || !el.classList) return;
    if (el.classList.contains("lnk") || el.classList.contains("lnk-act")) {
      var row = el.closest(".prow");
      var slot = row && row.nextElementSibling;
      if (slot && slot.classList.contains("slot") && slot.innerHTML.trim()) {
        slot.innerHTML = "";
        e.preventDefault();
      }
    }
  });

  // Ctrl/Cmd+K focuses search.
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      var i = document.querySelector(".sin");
      if (i) { i.focus(); i.select(); }
    }
  });

  // The sidebar highlight follows HTMX navigation, and Back.
  function mark() {
    var p = location.pathname;
    document.querySelectorAll(".side .nav").forEach(function (n) {
      var h = n.getAttribute("href") || "";
      n.classList.toggle("on", h === p);
    });
  }
  document.addEventListener("htmx:pushedIntoHistory", mark);
  window.addEventListener("popstate", function () { setTimeout(mark, 0); });

  // Header clock on the overview.
  setInterval(function () {
    var el = document.getElementById("clock");
    if (el) el.textContent = new Date().toTimeString().slice(0, 5);
  }, 30000);
})();
