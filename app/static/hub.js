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

  // Pipeline flow card: drag a node and its edges follow, drag the
  // background to pan, arrow keys nudge a focused node. Positions are a
  // per-viewer convenience in localStorage, keyed by the flow id; the
  // server layout (app/hub/flow.py) stays the default. Nothing here
  // navigates or scrolls the page.
  var NW = 148, NH = 38, PAD = 16, MOVED = 4;
  function store(id, v) {
    try {
      if (v) localStorage.setItem("hub-flow:" + id, JSON.stringify(v));
      else localStorage.removeItem("hub-flow:" + id);
    } catch (e) {}
  }
  function saved(id) {
    try { return JSON.parse(localStorage.getItem("hub-flow:" + id) || "null") || {}; }
    catch (e) { return {}; }
  }
  function num(v) { var r = Math.round(v * 100) / 100; return String(r); }
  // Same curve as flow._curve: right side of a to left side of b.
  function curve(ax, ay, bx, by) {
    var x1 = ax + NW, x2 = bx, dx = (x2 - x1) * 0.45;
    return "M" + num(x1) + " " + num(ay) + " C" + num(x1 + dx) + " " + num(ay) + " " +
      num(x2 - dx) + " " + num(by) + " " + num(x2) + " " + num(by);
  }
  function nodeOf(cv, k) {
    var all = cv.querySelectorAll(".node");
    for (var i = 0; i < all.length; i++) if (all[i].dataset.k === k) return all[i];
    return null;
  }
  function place(n, x, y) { n.style.left = x + "px"; n.style.top = y + "px"; }
  function pos(n) { return [parseFloat(n.style.left) || 0, parseFloat(n.style.top) || 0]; }
  function redraw(cv, k) {
    cv.querySelectorAll("path[data-s]").forEach(function (p) {
      if (k && p.dataset.s !== k && p.dataset.t !== k) return;
      var a = nodeOf(cv, p.dataset.s), b = nodeOf(cv, p.dataset.t);
      if (!a || !b) return;
      var pa = pos(a), pb = pos(b);
      p.setAttribute("d", curve(pa[0], pa[1] + NH / 2, pb[0], pb[1] + NH / 2));
    });
  }
  // The canvas grows to hold a node dragged past its edge, never shrinks
  // below the server's size, so nothing can be dropped out of reach.
  function fit(cv) {
    var w = +cv.dataset.w, h = +cv.dataset.h;
    cv.querySelectorAll(".node").forEach(function (n) {
      var p = pos(n);
      w = Math.max(w, p[0] + NW + PAD); h = Math.max(h, p[1] + NH + PAD);
    });
    cv.style.width = w + "px"; cv.style.height = h + "px";
    var svg = cv.querySelector("svg");
    if (svg) {
      svg.setAttribute("width", w); svg.setAttribute("height", h);
      svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    }
    var box = cv.closest(".flowbox");
    if (box && h > box.clientHeight) box.style.overflowY = "auto";
  }
  function card(cv) { return cv.closest(".flowcard"); }
  function showReset(cv) {
    var b = card(cv) && card(cv).querySelector(".flowreset");
    if (b) b.hidden = !Object.keys(saved(cv.dataset.flow)).length;
  }
  function remember(cv, n) {
    var s = saved(cv.dataset.flow), p = pos(n);
    s[n.dataset.k] = p;
    store(cv.dataset.flow, s);
    showReset(cv);
  }
  function initFlows() {
    document.querySelectorAll(".flowcanvas:not([data-ready])").forEach(function (cv) {
      cv.dataset.ready = "1";
      cv.dataset.w = parseFloat(cv.style.width) || cv.offsetWidth;
      cv.dataset.h = parseFloat(cv.style.height) || cv.offsetHeight;
      var s = saved(cv.dataset.flow);
      Object.keys(s).forEach(function (k) {
        var n = nodeOf(cv, k);
        if (n && s[k] && s[k].length === 2) place(n, Math.max(0, +s[k][0]), Math.max(0, +s[k][1]));
      });
      redraw(cv); fit(cv); showReset(cv);
    });
  }
  document.addEventListener("DOMContentLoaded", initFlows);
  document.addEventListener("htmx:afterSettle", initFlows);

  var drag = null;
  document.addEventListener("pointerdown", function (e) {
    if (e.button !== 0) return;
    var box = e.target.closest(".flowbox");
    var cv = box && box.querySelector(".flowcanvas");
    if (!cv) return;
    // A press on the box's own scrollbar scrolls as usual.
    if (e.target === box && (e.offsetX >= box.clientWidth || e.offsetY >= box.clientHeight)) return;
    var n = e.target.closest(".node");
    // The node you pick up stays on top of any it is dropped onto.
    if (n && n !== cv.lastElementChild) cv.appendChild(n);
    drag = n
      ? { kind: "node", cv: cv, n: n, x0: e.clientX, y0: e.clientY, p0: pos(n), moved: false }
      : { kind: "pan", box: box, x0: e.clientX, y0: e.clientY, s0: [box.scrollLeft, box.scrollTop], moved: false };
    (n || box).setPointerCapture(e.pointerId);
    (n || box).classList.add("grabbing");
    e.preventDefault();
  });
  document.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < MOVED) return;
    drag.moved = true;
    if (drag.kind === "pan") {
      drag.box.scrollLeft = drag.s0[0] - dx; drag.box.scrollTop = drag.s0[1] - dy;
      return;
    }
    place(drag.n, Math.max(0, Math.round(drag.p0[0] + dx)), Math.max(0, Math.round(drag.p0[1] + dy)));
    redraw(drag.cv, drag.n.dataset.k); fit(drag.cv);
  });
  function drop() {
    if (!drag) return;
    (drag.n || drag.box).classList.remove("grabbing");
    if (drag.kind === "node" && drag.moved) remember(drag.cv, drag.n);
    drag = null;
  }
  document.addEventListener("pointerup", drop);
  document.addEventListener("pointercancel", drop);

  document.addEventListener("keydown", function (e) {
    var n = e.target.closest && e.target.closest(".flowcanvas .node");
    var d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!n || !d) return;
    e.preventDefault();
    var cv = n.closest(".flowcanvas"), p = pos(n), step = e.shiftKey ? 40 : 10;
    place(n, Math.max(0, p[0] + d[0] * step), Math.max(0, p[1] + d[1] * step));
    redraw(cv, n.dataset.k); fit(cv); remember(cv, n);
  });

  // Hovering or focusing a node lights its own edges and fades the rest.
  function light(n, on) {
    var cv = n.closest(".flowcanvas");
    cv.classList.toggle("lit", on);
    cv.querySelectorAll("path[data-s]").forEach(function (p) {
      p.classList.toggle("hl", on && (p.dataset.s === n.dataset.k || p.dataset.t === n.dataset.k));
    });
  }
  ["mouseover", "focusin"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var n = e.target.closest && e.target.closest(".flowcanvas .node");
      if (n) light(n, true);
    });
  });
  ["mouseout", "focusout"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var n = e.target.closest && e.target.closest(".flowcanvas .node");
      if (n && !(e.relatedTarget && n.contains(e.relatedTarget))) light(n, false);
    });
  });

  document.addEventListener("click", function (e) {
    var b = e.target.closest(".flowreset");
    var cv = b && card(b) && b.closest(".flowcard").querySelector(".flowcanvas");
    if (!cv) return;
    store(cv.dataset.flow, null);
    cv.querySelectorAll(".node").forEach(function (n) { place(n, +n.dataset.x, +n.dataset.y); });
    redraw(cv); fit(cv); showReset(cv);
  });

  // Header clock on the overview.
  setInterval(function () {
    var el = document.getElementById("clock");
    if (el) el.textContent = new Date().toTimeString().slice(0, 5);
  }, 30000);
})();
