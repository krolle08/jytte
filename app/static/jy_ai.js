/* Shared behaviour for the new-design AI screens (mocks 1b, 1c, 1d).
 *
 * Carries the three rules forward from the previous build, which are
 * recorded in CLAUDE.md:
 *
 *   1. Nothing navigates. Selecting a workflow, a step or a context
 *      replaces content and pushes the URL with replaceState.
 *   2. Detail slides in from the right. Hover opens it, click pins it,
 *      Esc or the X dismisses it. Never under the element.
 *   3. The panel never covers what the pointer is on. On the
 *      constellation the canvas pans clear of it by the least amount
 *      that works.
 */
(function () {
  "use strict";

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)); };
  var el = function (t, c, txt) {
    var n = document.createElement(t);
    if (c) n.className = c;
    if (txt != null) n.textContent = txt;
    return n;
  };
  var raw = $("#ai-data");
  var D = (raw && raw.textContent.trim()) ? JSON.parse(raw.textContent) : {};
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function clearPressed() {
    $$("[aria-pressed='true']").forEach(function (n) {
      if (!n.closest(".seg")) n.setAttribute("aria-pressed", "false");
    });
  }

  /* ================= PANEL ================= */
  var panelEl = $("#jp");
  var panel = panelEl && (function () {
    var body = $("#jp-body"), foot = $("#jp-foot"), x = $("#jp-x");
    var pinned = false, timer = null, over = false, key = null;

    function stop() { if (timer) { clearTimeout(timer); timer = null; } }
    function show(k, render, pin) {
      stop();
      if (k !== key) {
        body.replaceChildren();
        foot.textContent = "";
        render(body, foot);
        key = k;
      }
      if (pin) pinned = true;
      panelEl.classList.add("is-open");
      panelEl.classList.toggle("is-pinned", pinned);
      panelEl.setAttribute("aria-hidden", "false");
    }
    function hide(now) {
      if (pinned && !now) return;
      stop();
      if (now) { commit(); return; }
      timer = setTimeout(function () { if (!over) commit(); }, 140);
    }
    function commit() {
      pinned = false; key = null;
      panelEl.classList.remove("is-open", "is-pinned");
      panelEl.setAttribute("aria-hidden", "true");
      clearPressed();
    }
    panelEl.addEventListener("pointerenter", function () { over = true; stop(); });
    panelEl.addEventListener("pointerleave", function () { over = false; hide(); });
    x.addEventListener("click", function () { hide(true); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && panelEl.classList.contains("is-open")) hide(true);
    });
    return {
      show: show, hide: hide,
      get pinned() { return pinned; },
      get open() { return panelEl.classList.contains("is-open"); }
    };
  })();

  function chip(txt, cls) { return el("span", "pill " + (cls || ""), txt); }

  function renderAgent(name) {
    var a = (D.agents || {})[name] || {};
    return function (b, f) {
      b.append(el("p", "jp-eye", "agent"));
      b.append(el("h3", null, name));
      var m = el("div", "jp-chips");
      m.append(chip(a.scope || "ukendt", a.scope === "global" ? "aqua" : ""));
      if (a.model) m.append(chip(a.model, "lilac"));
      m.append(chip((a.runs || 0) + " koersler"));
      if ((a.versions || 1) > 1) m.append(chip(a.versions + " versioner", "coral"));
      b.append(m);
      b.append(el("p", "jp-desc", a.d || "Ingen beskrivelse i frontmatter."));
      if (a.skills && a.skills.length) {
        b.append(el("h4", null, "Skills"));
        var s = el("div", "jp-chips");
        a.skills.forEach(function (n) {
          var btn = el("button", "pill aqua", n);
          btn.addEventListener("click", function (ev) {
            ev.stopPropagation();
            panel.show("skill:" + n, renderSkill(n), true);
          });
          s.append(btn);
        });
        b.append(s);
      }
      f.textContent = a.path || a.origin || "";
    };
  }

  function renderSkill(name) {
    var s = (D.skills || {})[name] || {};
    return function (b, f) {
      b.append(el("p", "jp-eye", "skill"));
      b.append(el("h3", null, name));
      var m = el("div", "jp-chips");
      m.append(chip(s.scope || "ukendt", s.scope === "global" ? "aqua" : ""));
      if ((s.versions || 1) > 1) m.append(chip(s.versions + " versioner", "coral"));
      if (s.orphan) m.append(chip("ingen ejer", "gul"));
      b.append(m);
      b.append(el("p", "jp-desc", s.d || "Ingen beskrivelse i frontmatter."));
      var owners = Object.keys(D.agents || {}).filter(function (a) {
        return ((D.agents[a].skills) || []).indexOf(name) >= 0;
      });
      if (owners.length) {
        b.append(el("h4", null, "Erklaeret af"));
        var o = el("div", "jp-chips");
        owners.forEach(function (n) {
          var btn = el("button", "pill lilac", n);
          btn.addEventListener("click", function (ev) {
            ev.stopPropagation();
            panel.show("agent:" + n, renderAgent(n), true);
          });
          o.append(btn);
        });
        b.append(o);
      }
      f.textContent = s.path || s.origin || "";
    };
  }

  /* Anything carrying data-agent or data-skill opens the panel. */
  function wire(node, k, render) {
    node.setAttribute("aria-pressed", "false");
    node.addEventListener("pointerenter", function () {
      if (panel.pinned) return;
      panel.show(k, render, false);
      reveal(node);
    });
    node.addEventListener("pointerleave", function () { panel.hide(); });
    node.addEventListener("focus", function () {
      reveal(node);
      if (!panel.pinned) panel.show(k, render, false);
    });
    node.addEventListener("click", function (e) {
      e.preventDefault();
      var on = node.getAttribute("aria-pressed") === "true";
      clearPressed();
      if (on) { panel.hide(true); return; }
      node.setAttribute("aria-pressed", "true");
      panel.show(k, render, true);
      reveal(node);
    });
  }

  /* ================= CONSTELLATION: PAN, ZOOM, FOCUS ================= */
  var sky = $("#jy-sky"), skyInner = $("#jy-sky-inner");
  var panX = 0, panY = 0, scale = 1, SLACK = 120, GAP = 26;
  var Z_MIN = 0.35, Z_MAX = 2.2;

  function panelLeft() {
    if (!panelEl || !panelEl.classList.contains("is-open")) return window.innerWidth;
    // offsetWidth, not the rect: the panel is mid-slide when this is
    // asked, so its live rect still reports off screen.
    var w = panelEl.offsetWidth || 0;
    return w ? window.innerWidth - w : window.innerWidth;
  }

  // The canvas is bigger than the viewport on purpose, so the clamp
  // works in SCALED pixels. Getting this wrong is what made panning
  // drift when zoomed.
  function clamp(x, y) {
    if (!sky || !skyInner) return [x, y];
    var vp = sky.getBoundingClientRect();
    var usable = Math.max(240, Math.min(vp.right, panelLeft()) - vp.left);
    var cw = skyInner.offsetWidth * scale, ch = skyInner.offsetHeight * scale;
    var loX = usable - cw - SLACK, hiX = SLACK;
    var loY = vp.height - ch - SLACK, hiY = SLACK;
    // When the field is smaller than the viewport there is nothing to
    // pan TO, but pinning it dead centre makes dragging feel broken -
    // the user asked for drag to move it, and a drag that does nothing
    // reads as a bug. So keep SLACK of play around the centre.
    if (loX > hiX) { var mx = (usable - cw) / 2; loX = mx - SLACK; hiX = mx + SLACK; }
    if (loY > hiY) { var my = (vp.height - ch) / 2; loY = my - SLACK; hiY = my + SLACK; }
    return [Math.max(loX, Math.min(hiX, x)), Math.max(loY, Math.min(hiY, y))];
  }

  function apply(anim) {
    if (!skyInner) return;
    skyInner.style.transition = (anim && !reduce)
      ? "transform .26s cubic-bezier(.2,.75,.3,1)" : "none";
    // One transform carries both, in this order: translate is in
    // viewport pixels, scale is about the top-left origin.
    skyInner.style.transform =
      "translate(" + panX + "px," + panY + "px) scale(" + scale + ")";
  }

  function setPan(x, y, anim) {
    var c = clamp(x, y);
    panX = c[0]; panY = c[1];
    apply(anim);
  }

  /* Zoom about a point, so whatever is under the cursor stays there. */
  function zoomAt(next, px, py, anim) {
    if (!sky) return;
    next = Math.max(Z_MIN, Math.min(Z_MAX, next));
    if (next === scale) return;
    var vp = sky.getBoundingClientRect();
    var cx = (px == null ? vp.width / 2 : px - vp.left);
    var cy = (py == null ? vp.height / 2 : py - vp.top);
    // The canvas point under the cursor before and after must match.
    var k = next / scale;
    panX = cx - (cx - panX) * k;
    panY = cy - (cy - panY) * k;
    scale = next;
    setPan(panX, panY, anim);
  }

  function fit(anim) {
    if (!sky || !skyInner) return;
    var vp = sky.getBoundingClientRect();
    var usable = Math.max(240, Math.min(vp.right, panelLeft()) - vp.left);
    scale = Math.max(Z_MIN, Math.min(1,
      Math.min((usable - 32) / skyInner.offsetWidth,
               (vp.height - 32) / skyInner.offsetHeight)));
    panX = (usable - skyInner.offsetWidth * scale) / 2;
    panY = (vp.height - skyInner.offsetHeight * scale) / 2;
    apply(anim);
  }

  /* Move a node clear of the panel by the least amount that works. An
   * element that always repositions slides out from under the cursor
   * and fires pointerleave on the very thing being read. */
  function reveal(node) {
    if (!sky || !skyInner) return;
    if (!node.closest || !node.closest("#jy-sky")) return;
    var vp = sky.getBoundingClientRect(), r = node.getBoundingClientRect();
    var right = Math.min(vp.right, panelLeft()) - GAP, left = vp.left + GAP;
    var dx = 0, dy = 0;
    if (r.right > right) dx = right - r.right;
    if (r.left + dx < left) dx = left - r.left;
    if (r.bottom > vp.bottom - GAP) dy = (vp.bottom - GAP) - r.bottom;
    if (r.top + dy < vp.top + GAP) dy = (vp.top + GAP) - r.top;
    if (dx || dy) setPan(panX + dx, panY + dy, true);
  }

  /* ---- focus: dim what is not related to the thing under the pointer.
   * With 14 agents and 44 skills on one field, dimming is what makes it
   * readable; it also reveals that agent's skill labels, which are off
   * by default because 44 labels at once cannot be read. */
  function focusAgent(name) {
    if (!sky) return;
    sky.classList.toggle("is-focused", !!name);
    $$(".jy-agent", sky).forEach(function (n) {
      n.classList.toggle("is-dim", !!name && n.dataset.agent !== name);
      n.classList.toggle("is-lit", !!name && n.dataset.agent === name);
    });
    $$(".jy-skill", sky).forEach(function (n) {
      var mine = n.dataset.owner === name;
      n.classList.toggle("is-dim", !!name && !mine);
      n.classList.toggle("is-lit", !!name && mine);
    });
    $$(".jy-edge", sky).forEach(function (e) {
      e.classList.toggle("is-dim", !!name && e.dataset.agent !== name);
      e.classList.toggle("is-lit", !!name && e.dataset.agent === name);
    });
  }

  function focusSkill(name) {
    if (!sky) return;
    var owners = Object.keys(D.agents || {}).filter(function (a) {
      return ((D.agents[a].skills) || []).indexOf(name) >= 0;
    });
    sky.classList.toggle("is-focused", !!name);
    $$(".jy-agent", sky).forEach(function (n) {
      var mine = owners.indexOf(n.dataset.agent) >= 0;
      n.classList.toggle("is-dim", !!name && !mine);
      n.classList.toggle("is-lit", !!name && mine);
    });
    $$(".jy-skill", sky).forEach(function (n) {
      var mine = n.dataset.skill === name;
      n.classList.toggle("is-dim", !!name && !mine);
      n.classList.toggle("is-lit", !!name && mine);
    });
    $$(".jy-edge", sky).forEach(function (e) {
      var mine = owners.indexOf(e.dataset.agent) >= 0;
      e.classList.toggle("is-dim", !!name && !mine);
      e.classList.toggle("is-lit", !!name && mine);
    });
  }

  if (sky && skyInner) {
    $$(".jy-agent", sky).forEach(function (n) {
      n.addEventListener("pointerenter", function () { focusAgent(n.dataset.agent); });
      n.addEventListener("focus", function () { focusAgent(n.dataset.agent); });
    });
    $$(".jy-skill", sky).forEach(function (n) {
      n.addEventListener("pointerenter", function () { focusSkill(n.dataset.skill); });
      n.addEventListener("focus", function () { focusSkill(n.dataset.skill); });
    });

    /* ---- drag to pan ---- */
    var drag = false, sx = 0, sy = 0, ox = 0, oy = 0, moved = false;
    sky.addEventListener("pointerdown", function (e) {
      if (e.target.closest("[data-agent],[data-skill],button,a")) return;
      drag = true; moved = false;
      sx = e.clientX; sy = e.clientY; ox = panX; oy = panY;
      try { sky.setPointerCapture(e.pointerId); } catch (ignored) {}
      sky.classList.add("is-dragging");
    });
    sky.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      setPan(ox + dx, oy + dy, false);
    });
    var endDrag = function (e) {
      if (!drag) return;
      drag = false;
      sky.classList.remove("is-dragging");
      try { sky.releasePointerCapture(e.pointerId); } catch (ignored) {}
      setPan(panX, panY, true);
    };
    sky.addEventListener("pointerup", endDrag);
    sky.addEventListener("pointercancel", endDrag);

    // Leaving the field drops the focus and an unpinned panel.
    sky.addEventListener("pointerleave", function () {
      if (!drag) focusAgent(null);
      if (panel) panel.hide();
    });

    /* ---- wheel to zoom about the pointer ---- */
    sky.addEventListener("wheel", function (e) {
      // The field is a fixed-height viewport, so the page has nothing
      // to scroll here; taking the wheel is what a graph should do.
      e.preventDefault();
      var step = e.deltaY > 0 ? 0.88 : 1.14;
      zoomAt(scale * step, e.clientX, e.clientY, false);
    }, { passive: false });

    sky.addEventListener("dblclick", function () { fit(true); });

    /* ---- keyboard: arrows pan, +/- zoom ---- */
    sky.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? 240 : 80, hit = true;
      if (e.key === "ArrowLeft") setPan(panX + step, panY, true);
      else if (e.key === "ArrowRight") setPan(panX - step, panY, true);
      else if (e.key === "ArrowUp") setPan(panX, panY + step, true);
      else if (e.key === "ArrowDown") setPan(panX, panY - step, true);
      else if (e.key === "+" || e.key === "=") zoomAt(scale * 1.18, null, null, true);
      else if (e.key === "-") zoomAt(scale / 1.18, null, null, true);
      else if (e.key === "0") fit(true);
      else hit = false;
      if (hit) e.preventDefault();
    });

    var zi = $("#jy-zin"), zo = $("#jy-zout"), zf = $("#jy-zfit");
    if (zi) zi.addEventListener("click", function () { zoomAt(scale * 1.18, null, null, true); });
    if (zo) zo.addEventListener("click", function () { zoomAt(scale / 1.18, null, null, true); });
    if (zf) zf.addEventListener("click", function () { fit(true); });

    // Open centred on the field rather than on its top-left corner,
    // which was empty space.
    fit(false);
    window.addEventListener("resize", function () { setPan(panX, panY, false); });
  }

  if (panel) {
    $$("[data-agent]").forEach(function (n) {
      wire(n, "agent:" + n.dataset.agent, renderAgent(n.dataset.agent));
    });
    $$("[data-skill]").forEach(function (n) {
      wire(n, "skill:" + n.dataset.skill, renderSkill(n.dataset.skill));
    });
  }

  /* ================= TABLE FILTERS (1b) ================= */
  (function () {
    var bar = $("#ai2-filters");
    if (!bar) return;
    var rows = $$(".ai2-tr");
    var T = {
      all: function () { return true; },
      agent: function (r) { return r.dataset.kind === "agent"; },
      skill: function (r) { return r.dataset.kind === "skill"; },
      global: function (r) { return r.dataset.scope === "global"; },
      project: function (r) { return r.dataset.scope === "project"; },
      both: function (r) { return r.dataset.scope === "both"; },
      merge: function (r) { return r.dataset.merge === "1"; }
    };
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-f]");
      if (!b) return;
      var t = T[b.dataset.f] || T.all;
      $$("button", bar).forEach(function (x) {
        x.setAttribute("aria-pressed", String(x === b));
      });
      rows.forEach(function (r) { r.hidden = !t(r); });
    });
  })();

  /* ================= WORKFLOW PULSE (1d) ================= */
  var stage = $("#jy-flow");
  if (stage && !reduce && Element.prototype.animate) {
    var SVGNS = "http://www.w3.org/2000/svg";
    var fire = function () {
      if (document.hidden) return;
      $$("path[data-straight='1']", stage).forEach(function (p, i) {
        var len = p.getTotalLength();
        if (!len) return;
        var dot = document.createElementNS(SVGNS, "circle");
        dot.setAttribute("r", "3.4");
        dot.setAttribute("class", "jy-spark");
        p.parentNode.append(dot);
        var a = dot.animate([{ offsetDistance: "0%" }, { offsetDistance: "100%" }],
                            { duration: 620, delay: i * 180, easing: "ease-in-out" });
        dot.style.offsetPath = "path('" + p.getAttribute("d") + "')";
        a.onfinish = function () { dot.remove(); };
      });
    };
    fire();
    setInterval(fire, 5000);
  }
})();
