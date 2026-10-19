/* AI architecture view - canvas and slide-in detail panel.
 *
 * Two rules drive the whole file:
 *
 *   1. Nothing here navigates. Selecting a workflow replaces the canvas
 *      and pushes a URL; it never loads a page, because a page load
 *      throws the viewport back to the top and you lose your place.
 *
 *   2. The detail panel has two modes, and they behave differently on
 *      purpose. HOVER is transient: it opens on pointer-in and closes
 *      on pointer-out. PINNED is deliberate: a click keeps it open
 *      until Esc or the X. Moving onto the panel itself never closes
 *      it, or a long description would be unreadable.
 */
(function () {
  "use strict";

  var raw = document.getElementById("ai-data");
  if (!raw) return;
  var D = JSON.parse(raw.textContent);

  var $ = function (s) { return document.querySelector(s); };
  var el = function (t, c, txt) {
    var n = document.createElement(t);
    if (c) n.className = c;
    if (txt != null) n.textContent = txt;
    return n;
  };
  var SVGNS = "http://www.w3.org/2000/svg";
  var sv = function (t, at) {
    var n = document.createElementNS(SVGNS, t);
    for (var k in at) n.setAttribute(k, at[k]);
    return n;
  };
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ================= TABS ================= */
  var TABS = [["tab-sky", "view-sky"], ["tab-flow", "view-flow"]];
  TABS.forEach(function (pair) {
    var btn = document.getElementById(pair[0]);
    if (!btn) return;
    btn.addEventListener("click", function () {
      TABS.forEach(function (p) {
        var on = p[0] === pair[0];
        document.getElementById(p[0]).setAttribute("aria-selected", String(on));
        document.getElementById(p[1]).hidden = !on;
      });
      // Switching away from the sky leaves a hover panel with nothing
      // behind it, so drop it. A pinned one is a deliberate choice and
      // survives.
      if (pair[0] === "tab-flow" && !panel.pinned) panel.hide(true);
      if (fitPending && pair[0] === "tab-flow") { fitPending = false; fit(); }
    });
  });

  /* ================= SLIDE-IN PANEL ================= */
  var panelEl = $("#ai-panel");
  var panel = (function () {
    var root = panelEl,
        body = $("#ai-panel-body"),
        foot = $("#ai-panel-foot"),
        xbtn = $("#ai-panel-x");
    var pinned = false, closeTimer = null, overPanel = false, lastKey = null;

    function cancelClose() { if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; } }

    function show(key, render, pin) {
      cancelClose();
      if (key !== lastKey) { body.replaceChildren(); foot.textContent = ""; render(body, foot); lastKey = key; }
      if (pin) pinned = true;
      root.classList.add("is-open");
      root.classList.toggle("is-pinned", pinned);
      root.setAttribute("aria-hidden", "false");
    }

    // A short grace period, so moving the pointer from one orb to the
    // next, or out to the panel, does not flash it closed and open.
    function hide(now) {
      if (pinned && !now) return;
      cancelClose();
      if (now) { commit(); return; }
      closeTimer = setTimeout(function () { if (!overPanel) commit(); }, 140);
    }

    function commit() {
      pinned = false;
      root.classList.remove("is-open", "is-pinned");
      root.setAttribute("aria-hidden", "true");
      lastKey = null;
      document.querySelectorAll(".ai-body[aria-pressed='true'], .ai-chip[aria-pressed='true']")
        .forEach(function (n) { n.setAttribute("aria-pressed", "false"); });
    }

    root.addEventListener("pointerenter", function () { overPanel = true; cancelClose(); });
    root.addEventListener("pointerleave", function () { overPanel = false; hide(); });
    xbtn.addEventListener("click", function () {
      hide(true);
      returnFocusTo(lastAgent ? ".ai-body[data-agent='" + lastAgent + "']" : null);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && root.classList.contains("is-open")) {
        hide(true);
        returnFocusTo(lastAgent ? ".ai-body[data-agent='" + lastAgent + "']" : null);
      }
    });

    return {
      show: show, hide: hide,
      get pinned() { return pinned; },
      set pinned(v) { pinned = v; }
    };
  })();

  var lastAgent = null;
  // Esc and the X hand focus back to the thing that opened the panel,
  // which is right for keyboard users but fires the focus handler and
  // reopened the panel immediately. Suppress that one focus event.
  var suppressFocusOpen = false;

  function returnFocusTo(sel) {
    var t = sel && document.querySelector(sel);
    if (!t) return;
    suppressFocusOpen = true;
    t.focus();
    setTimeout(function () { suppressFocusOpen = false; }, 0);
  }

  function chip(text, cls) { return el("span", "ai-chip is-static" + (cls ? " " + cls : ""), text); }

  function renderAgent(name) {
    var a = D.agents[name] || {};
    return function (body, foot) {
      body.append(el("p", "ai-panel-eyebrow", "agent"));
      body.append(el("h3", null, name));
      var meta = el("div", "ai-panel-chips");
      meta.append(chip(a.scope || "ukendt scope", a.scope === "global" ? "is-gold" : ""));
      if (a.model) meta.append(chip(a.model));
      meta.append(chip(a.runs ? a.runs + " kørsler" : "aldrig kørt"));
      if (a.versions > 1) meta.append(chip(a.versions + " versioner", "is-alarm"));
      if (a.copies > 1) meta.append(chip(a.copies + " kopier"));
      body.append(meta);
      body.append(el("p", "ai-panel-desc", a.d || "Ingen beskrivelse i frontmatter."));

      body.append(el("h4", null, "Skills"));
      var sk = el("div", "ai-panel-chips");
      if (a.skills && a.skills.length) {
        a.skills.forEach(function (s) {
          var c = el("button", "ai-chip" + (D.skills[s] ? "" : " is-alarm"), s);
          if (!D.skills[s]) c.title = "erklæret, men ikke fundet på disk";
          c.addEventListener("click", function (ev) {
            ev.stopPropagation();
            panel.show("skill:" + s, renderSkill(s), true);
          });
          sk.append(c);
        });
      } else {
        sk.append(chip("ingen erklæret"));
      }
      body.append(sk);

      if (a.mcp && a.mcp.length) {
        body.append(el("h4", null, "MCP"));
        var mc = el("div", "ai-panel-chips");
        a.mcp.forEach(function (m) { mc.append(chip(m)); });
        body.append(mc);
      }

      var flows = flowsTouching(name);
      if (flows.length) {
        body.append(el("h4", null, "Bruges i"));
        var fl = el("div", "ai-panel-chips");
        flows.forEach(function (id) {
          var b = el("button", "ai-chip", D.workflows[id].n);
          b.addEventListener("click", function (ev) {
            ev.stopPropagation();
            openFlow(id);
          });
          fl.append(b);
        });
        body.append(fl);
      }
      foot.textContent = a.path || a.origin || "";
    };
  }

  function renderSkill(name) {
    var s = D.skills[name] || {};
    return function (body, foot) {
      body.append(el("p", "ai-panel-eyebrow", "skill"));
      body.append(el("h3", null, name));
      var meta = el("div", "ai-panel-chips");
      meta.append(chip(s.scope || "ukendt scope", s.scope === "global" ? "is-gold" : ""));
      if (s.versions > 1) meta.append(chip(s.versions + " versioner", "is-alarm"));
      if (s.copies > 1) meta.append(chip(s.copies + " kopier"));
      if (s.orphan) meta.append(chip("ingen agent erklærer den"));
      body.append(meta);
      body.append(el("p", "ai-panel-desc", s.d || "Ingen beskrivelse i frontmatter."));

      var owners = Object.keys(D.agents).filter(function (a) {
        return (D.agents[a].skills || []).indexOf(name) >= 0;
      });
      if (owners.length) {
        body.append(el("h4", null, "Erklæret af"));
        var ow = el("div", "ai-panel-chips");
        owners.forEach(function (o) {
          var b = el("button", "ai-chip", o);
          b.addEventListener("click", function (ev) {
            ev.stopPropagation();
            lastAgent = o;
            panel.show("agent:" + o, renderAgent(o), true);
          });
          ow.append(b);
        });
        body.append(ow);
      }
      foot.textContent = s.path || s.origin || "";
    };
  }

  function renderNode(wid, node) {
    return function (body, foot) {
      body.append(el("p", "ai-panel-eyebrow", node.k));
      body.append(el("h3", null, node.w));
      body.append(el("p", "ai-panel-desc", node.y || "Ingen note på trinnet."));
      if (node.r) {
        var isSkill = !!D.skills[node.r];
        // Direction differs by engine. A vault step invokes what it
        // names; an n8n node is the other way round, the skill is what
        // calls that webhook, which is why it carries its name.
        var n8n = D.workflows[wid].eng === "n8n";
        body.append(el("h4", null, n8n ? "Kaldes af" : "Kalder"));
        var box = el("div", "ai-panel-chips");
        var b = el("button", "ai-chip", node.r);
        b.addEventListener("click", function (ev) {
          ev.stopPropagation();
          if (isSkill) panel.show("skill:" + node.r, renderSkill(node.r), true);
          else { lastAgent = node.r; panel.show("agent:" + node.r, renderAgent(node.r), true); }
        });
        box.append(b);
        body.append(box);
      }
      foot.textContent = D.workflows[wid].source || "";
    };
  }

  function flowsTouching(name) {
    return Object.keys(D.workflows).filter(function (id) {
      return D.workflows[id].nodes.some(function (n) { return n.r === name; });
    });
  }

  /* ---- wiring the constellation to the panel ---- */
  function wireHover(node, key, render) {
    node.setAttribute("aria-pressed", "false");

    node.addEventListener("pointerenter", function () {
      if (panel.pinned) return;          // a pinned panel is not hijacked by a hover
      panel.show(key, render, false);
      // The panel has just taken the right edge of the screen, so the
      // thing being pointed at may now be under it.
      if (node.classList.contains("ai-body")) reveal(node);
    });
    node.addEventListener("pointerleave", function () { panel.hide(); });
    node.addEventListener("focus", function () {
      if (node.classList.contains("ai-body")) reveal(node);
      if (suppressFocusOpen || panel.pinned) return;
      panel.show(key, render, false);
    });
    node.addEventListener("click", function () {
      if (node.classList.contains("ai-body")) reveal(node);
      var already = node.getAttribute("aria-pressed") === "true";
      document.querySelectorAll("[aria-pressed='true']").forEach(function (n) {
        n.setAttribute("aria-pressed", "false");
      });
      if (already) { panel.hide(true); return; }
      node.setAttribute("aria-pressed", "true");
      panel.show(key, render, true);
    });
  }

  /* ================= PANNING SKY =================
   * The detail panel is fixed to the right edge, so anything under it
   * was unclickable and un-hoverable - you could not reach the next
   * agent without the panel in the way. So the field became a viewport
   * over a fixed canvas:
   *
   *   - drag anywhere on empty space to move the field
   *   - hovering or focusing an agent pans it clear of the panel, by
   *     the smallest amount that works, never more
   *   - the pan is clamped so the content can never be dragged further
   *     than SLACK px past the edge of the viewport, so you cannot get
   *     lost in empty space
   *
   * Why "the smallest amount that works" and not "always put it beside
   * the panel": an element that moves on hover slides out from under
   * the cursor, which fires pointerleave on the thing you are trying
   * to look at. Moving only when it is actually occluded keeps the
   * field still for every agent that was already reachable.
   */
  var sky = $("#ai-sky"), skyCanvas = $("#ai-sky-canvas");
  var panX = 0, panY = 0, SLACK = 150, REVEAL_GAP = 26;

  // Under 760px the field stacks as a list and the panel is a bottom
  // sheet, so there is nothing to pan clear of. Mirrors the breakpoint
  // in styles.css; kept in sync by the class this sets.
  var narrow = window.matchMedia("(max-width: 760px)");
  var isStatic = narrow.matches;
  function syncStatic() {
    isStatic = narrow.matches;
    if (sky) sky.classList.toggle("is-static", isStatic);
    if (isStatic && skyCanvas) {
      skyCanvas.style.transform = "";
      panX = panY = 0;
    }
  }
  if (narrow.addEventListener) narrow.addEventListener("change", syncStatic);
  else if (narrow.addListener) narrow.addListener(syncStatic);

  function panelLeftEdge() {
    // The whole viewport is usable when the panel is shut.
    if (!panelEl.classList.contains("is-open")) return window.innerWidth;
    // Deliberately offsetWidth and not getBoundingClientRect(): the
    // panel is mid-slide at the moment this is asked, so its live rect
    // is still off screen and would report "nothing is covered".
    var w = panelEl.offsetWidth || 0;
    return w ? window.innerWidth - w : window.innerWidth;
  }

  function clampPan(x, y) {
    if (!sky || !skyCanvas || isStatic) return [0, 0];
    var vp = sky.getBoundingClientRect();
    var usableW = Math.max(220, Math.min(vp.right, panelLeftEdge()) - vp.left);
    var cw = skyCanvas.offsetWidth, ch = skyCanvas.offsetHeight;
    var loX = usableW - cw - SLACK, hiX = SLACK;
    var loY = vp.height - ch - SLACK, hiY = SLACK;
    if (loX > hiX) { loX = -SLACK; hiX = usableW - cw + SLACK; }
    if (loY > hiY) { loY = -SLACK; hiY = vp.height - ch + SLACK; }
    return [Math.max(loX, Math.min(hiX, x)), Math.max(loY, Math.min(hiY, y))];
  }

  function setPan(x, y, animate) {
    var c = clampPan(x, y);
    panX = c[0]; panY = c[1];
    if (!skyCanvas) return;
    skyCanvas.style.transition = (animate && !reduceMotion)
      ? "transform .26s cubic-bezier(.2,.75,.3,1)" : "none";
    skyCanvas.style.transform = "translate(" + panX + "px," + panY + "px)";
  }

  /* Move an agent clear of the panel and inside the viewport, by the
   * least amount that does it. */
  function reveal(node) {
    if (!sky || !skyCanvas || isStatic) return;
    var vp = sky.getBoundingClientRect();
    var r = node.getBoundingClientRect();
    var right = Math.min(vp.right, panelLeftEdge()) - REVEAL_GAP;
    var left = vp.left + REVEAL_GAP;
    var dx = 0, dy = 0;

    if (r.right > right) dx = right - r.right;
    if (r.left + dx < left) dx = left - r.left;
    if (r.bottom > vp.bottom - REVEAL_GAP) dy = (vp.bottom - REVEAL_GAP) - r.bottom;
    if (r.top + dy < vp.top + REVEAL_GAP) dy = (vp.top + REVEAL_GAP) - r.top;

    if (dx || dy) setPan(panX + dx, panY + dy, true);
  }

  /* ---- drag ---- */
  (function () {
    if (!sky) return;
    var dragging = false, sx = 0, sy = 0, ox = 0, oy = 0, moved = false;

    syncStatic();

    sky.addEventListener("pointerdown", function (e) {
      // Let the agents keep their own clicks.
      if (e.target.closest(".ai-body")) return;
      if (isStatic) return;
      dragging = true; moved = false;
      sx = e.clientX; sy = e.clientY; ox = panX; oy = panY;
      // Capture is an optimisation - it keeps the drag alive when the
      // pointer leaves the box. It throws on an unknown pointerId, so
      // a failure must not take the drag down with it.
      try { sky.setPointerCapture(e.pointerId); } catch (_) {}
      sky.classList.add("is-dragging");
    });
    sky.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      setPan(ox + dx, oy + dy, false);
    });
    function end(e) {
      if (!dragging) return;
      dragging = false;
      sky.classList.remove("is-dragging");
      try { sky.releasePointerCapture(e.pointerId); } catch (_) {}
      // Snap back inside the slack the drag was allowed to overshoot.
      setPan(panX, panY, true);
    }
    sky.addEventListener("pointerup", end);
    sky.addEventListener("pointercancel", end);

    // A panel left open over a field nobody is pointing at is clutter.
    sky.addEventListener("pointerleave", function () { panel.hide(); });

    // Reclamp when the panel opens or closes, or the window resizes:
    // both change how much width is usable.
    window.addEventListener("resize", function () { setPan(panX, panY, false); });
  })();

  document.querySelectorAll(".ai-body").forEach(function (n) {
    var name = n.dataset.agent;
    wireHover(n, "agent:" + name, function (b, f) {
      lastAgent = name;
      renderAgent(name)(b, f);
    });
  });
  // Every element that names a skill or an agent opens the same panel,
  // wherever it lives: orphan chips, merge-candidate chips in the
  // summary, and the name column of the ledger.
  document.querySelectorAll("[data-skill]").forEach(function (n) {
    wireHover(n, "skill:" + n.dataset.skill, renderSkill(n.dataset.skill));
  });
  document.querySelectorAll("[data-agent]:not(.ai-body)").forEach(function (n) {
    var name = n.dataset.agent;
    wireHover(n, "agent:" + name, function (b, f) {
      lastAgent = name;
      renderAgent(name)(b, f);
    });
  });

  /* ================= LEDGER FILTERS ================= */
  (function () {
    var bar = $("#ai-filters");
    if (!bar) return;
    var rows = [].slice.call(document.querySelectorAll(".ai-table tbody tr"));
    var TEST = {
      all:     function () { return true; },
      agent:   function (r) { return r.dataset.kind === "agent"; },
      skill:   function (r) { return r.dataset.kind === "skill"; },
      global:  function (r) { return r.dataset.scope === "global"; },
      project: function (r) { return r.dataset.scope === "project"; },
      both:    function (r) { return r.dataset.scope === "both"; },
      merge:   function (r) { return r.dataset.merge === "1"; },
      cold:    function (r) { return r.dataset.cold === "1"; }
    };
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-f]");
      if (!b) return;
      var f = b.dataset.f, test = TEST[f] || TEST.all;
      bar.querySelectorAll("button").forEach(function (x) {
        x.setAttribute("aria-pressed", String(x === b));
      });
      var shown = 0;
      rows.forEach(function (r) {
        var on = test(r);
        r.hidden = !on;
        if (on) shown++;
      });
      bar.setAttribute("data-shown", shown);
    });
  })();

  /* ================= WORKFLOW RAIL ================= */
  var rail = $("#ai-rail");
  (D.themes || []).forEach(function (th) {
    var g = el("div", "ai-rail-group");
    g.append(el("h3", null, th.name));
    (th.projects || []).forEach(function (pr) {
      g.append(el("p", "ai-rail-proj", pr.name));
      (pr.wfs || []).forEach(function (id) {
        var w = D.workflows[id];
        if (!w) return;
        var b = el("button", "ai-rail-item");
        b.dataset.wf = id;
        b.setAttribute("aria-current", "false");
        b.append(el("span", "ai-rail-n", w.n));
        b.append(el("span", "ai-rail-c", w.cols + " trin dybt"));
        b.append(el("span", "ai-dot " + (w.c || "")));
        b.addEventListener("click", function () { selectFlow(id, true); });
        g.append(b);
      });
    });
    rail.append(g);
  });

  /* ================= CANVAS ================= */
  var STEP = 198, LANE = 136, CW = 168;
  var stage = $("#ai-stage"), scroll = $("#ai-scroll");
  var zoom = 1, current = null, fitPending = true;
  // The pulse repeats rather than firing once on select, so the flow
  // keeps showing its direction while you read it. Held here so the
  // interval can re-fire it against whatever is currently drawn.
  var livePulse = null, PULSE_EVERY = 5000;

  function openFlow(id) {
    document.getElementById("tab-flow").click();
    selectFlow(id, true);
  }

  function selectFlow(id, pushUrl) {
    var w = D.workflows[id];
    if (!w) return;
    current = id;

    document.querySelectorAll(".ai-rail-item").forEach(function (n) {
      n.setAttribute("aria-current", String(n.dataset.wf === id));
    });

    $("#ai-wf-title").textContent = w.n;
    $("#ai-wf-eng").textContent = w.eng;
    $("#ai-wf-run").textContent = w.run;
    $("#ai-wf-desc").textContent = w.desc
      || (w.project + " / " + w.theme + ". Kilden har ingen beskrivelse, så titlen er alt der er.");
    $("#ai-wf-src").textContent = w.source || "";

    draw(w);

    // Deep link without navigating: the URL follows the selection, the
    // viewport does not move.
    if (pushUrl && window.history && history.replaceState) {
      // location.pathname, not a hardcoded "/ai": this page moved to
      // /legacy/ai when the new dark shell took the canonical paths,
      // and a hardcoded path rewrote the URL to a different page - so
      // reloading landed somewhere you were not.
      history.replaceState(null, "", location.pathname + "?wf=" + encodeURIComponent(id));
    }
  }

  function draw(w) {
    stage.replaceChildren();
    var maxRow = Math.max.apply(null, w.nodes.map(function (n) { return n.row; }));
    var H = (maxRow + 1) * LANE + 130;
    var W = w.cols * STEP + 60;
    stage.style.height = H + "px";
    stage.style.width = W + "px";

    var pos = {};
    w.nodes.forEach(function (n) {
      pos[n.id] = { x: n.col * STEP + 14, y: n.row * LANE + 64 };
    });

    var svg = sv("svg", { width: W, height: H });
    stage.append(svg);

    var straightSegs = [];

    // Orthogonal routing: out the right, across, in the left. A branch
    // therefore leaves the line at a visible right angle instead of a
    // soft curve that reads like the main path.
    w.e.forEach(function (e) {
      var a = pos[e.s], b = pos[e.t];
      if (!a || !b) return;
      var x1 = a.x + CW, x2 = b.x, mid = x1 + Math.max(20, (x2 - x1) / 2), d;
      if (e.straight) {
        d = "M" + x1 + "," + a.y + " L" + x2 + "," + b.y;
        straightSegs.push([a, b]);
      } else {
        var dir = b.y > a.y ? 1 : -1;
        d = "M" + x1 + "," + a.y
          + " L" + (mid - 10) + "," + a.y
          + " Q" + mid + "," + a.y + " " + mid + "," + (a.y + dir * 10)
          + " L" + mid + "," + (b.y - dir * 10)
          + " Q" + mid + "," + b.y + " " + (mid + 10) + "," + b.y
          + " L" + x2 + "," + b.y;
      }
      svg.append(sv("path", {
        d: d, fill: "none",
        stroke: e.back ? "var(--ai-alarm)" : (e.straight ? "var(--ai-edge)" : "var(--ai-calm)"),
        "stroke-width": e.straight ? 1.6 : 1.2,
        "stroke-dasharray": e.back ? "5 4" : "",
        "stroke-linecap": "round"
      }));

      if (e.l) {
        var lab = el("span", "ai-elabel", e.l);
        lab.style.left = mid + "px";
        lab.style.top = (a.y + (b.y - a.y) / 2) + "px";
        stage.append(lab);
      }
    });

    w.nodes.forEach(function (n) {
      var c = el("button", "ai-cell k-" + n.k);
      c.style.left = pos[n.id].x + "px";
      c.style.top = pos[n.id].y + "px";
      c.append(el("span", "ai-cell-k", n.k));
      c.append(el("span", "ai-cell-w", n.w));
      if (n.y) c.append(el("span", "ai-cell-y", n.y));
      wireHover(c, "node:" + current + ":" + n.id, renderNode(current, n));
      stage.append(c);

      // Detour lane: everything a step reaches sideways for, below the
      // chain on a dashed drop. Skill and agent carry data today; MCP
      // and memory are in the contract and shown empty until the
      // scanner reads them, rather than hidden.
      var drops = [];
      if (n.r) drops.push([D.skills[n.r] ? "skill" : "agent", n.r, false]);
      if (n.col === 0) drops.push(["mcp", "ikke scannet endnu", true]);

      drops.forEach(function (dp, i) {
        var dy = pos[n.id].y + 58 + i * 48;
        svg.append(sv("path", {
          d: "M" + (pos[n.id].x + 26) + "," + (pos[n.id].y + 26)
             + " L" + (pos[n.id].x + 26) + "," + (dy + 15),
          fill: "none", stroke: dp[2] ? "var(--ai-line)" : "var(--ai-edge)",
          "stroke-dasharray": "3 3", "stroke-width": 1
        }));
        var box = el(dp[2] ? "div" : "button", "ai-drop is-" + dp[0] + (dp[2] ? " is-empty" : ""));
        box.style.left = (pos[n.id].x + 16) + "px";
        box.style.top = dy + "px";
        box.append(el("span", "ai-drop-k", dp[0]));
        box.append(el("span", "ai-drop-w", dp[1]));
        if (!dp[2]) {
          var isSkill = dp[0] === "skill";
          wireHover(box, (isSkill ? "skill:" : "agent:") + dp[1],
                    isSkill ? renderSkill(dp[1]) : renderAgent(dp[1]));
        }
        stage.append(box);
      });
    });

    livePulse = { svg: svg, segs: straightSegs };
    pulse(svg, straightSegs);
  }

  // One timer for the page, not one per redraw: a new flow replaces
  // livePulse, so switching flows can never leave an old timer firing
  // at a detached SVG.
  setInterval(function () {
    if (!livePulse || reduceMotion) return;
    if (document.hidden) return;                       // no work in a background tab
    if (document.getElementById("view-flow").hidden) return;  // not on screen
    pulse(livePulse.svg, livePulse.segs);
  }, PULSE_EVERY);

  /* One dot per straight segment, released in sequence. Cheap, and it
   * answers "which way does this run" without a single arrowhead. */
  function pulse(svg, segs) {
    if (reduceMotion || !segs.length || !Element.prototype.animate) return;
    segs.forEach(function (seg, i) {
      var a = seg[0], b = seg[1];
      var dot = sv("circle", { r: 3.6, cx: a.x + CW, cy: a.y, class: "ai-spark" });
      svg.append(dot);
      var dist = b.x - a.x - CW;
      var anim = dot.animate([
        { transform: "translateX(0px)", opacity: 0 },
        { transform: "translateX(" + (dist * 0.5) + "px)", opacity: 1 },
        { transform: "translateX(" + dist + "px)", opacity: 0 }
      ], { duration: 620, delay: i * 190, easing: "ease-in-out" });
      anim.onfinish = function () { dot.remove(); };
    });
  }

  /* ---- zoom. Real flows are 5 to 9 columns wide. ---- */
  function applyZoom() {
    stage.style.transform = "scale(" + zoom + ")";
    var w = parseFloat(stage.style.width) || 0, h = parseFloat(stage.style.height) || 0;
    stage.style.marginRight = (w * (zoom - 1)) + "px";
    stage.style.marginBottom = (h * (zoom - 1)) + "px";
  }
  function fit() {
    var avail = scroll.clientWidth - 26;
    var w = parseFloat(stage.style.width) || 1;
    zoom = Math.max(0.45, Math.min(1, avail / w));
    applyZoom();
  }
  $("#ai-zoom-in").addEventListener("click", function () { zoom = Math.min(1.6, zoom + 0.15); applyZoom(); });
  $("#ai-zoom-out").addEventListener("click", function () { zoom = Math.max(0.45, zoom - 0.15); applyZoom(); });
  $("#ai-zoom-fit").addEventListener("click", fit);
  $("#ai-replay").addEventListener("click", function () {
    if (livePulse) pulse(livePulse.svg, livePulse.segs);
  });

  if (D.selected) selectFlow(D.selected, false);
  // Open on the Workflows tab when the URL asked for a specific flow.
  if (new URLSearchParams(location.search).get("wf")) {
    document.getElementById("tab-flow").click();
  }
})();
