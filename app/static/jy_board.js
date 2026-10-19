/* Panel board: equal cells, drag to reorder, click to collapse.
 *
 * WHY THIS EXISTS
 * Panels were single-column and stretched to the full width of the
 * main area. On a wide monitor that left a pipeline row with its name
 * on the far left and its status 1500px away on the right, which is
 * unreadable. Panels now sit two per row in equal cells, and each one
 * can be collapsed or moved.
 *
 * Markup contract, so templates stay clean:
 *   <div class="board" data-board="devops">          one board per page
 *     <section class="pn" data-card="pipelines">     one card per panel
 *       <div class="pn-h"> ... </div>                becomes the handle
 *
 * A card may set data-span="2" to keep the full row (a flow canvas).
 *
 * Order and collapsed state persist per page in localStorage. Reading
 * it is wrapped: a private window or cleared site data makes it throw,
 * and a board that cannot remember its order must still work.
 */
(function () {
  "use strict";

  var $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)); };

  function key(board) { return "jy.board." + location.pathname + "." + board.dataset.board; }

  function load(board) {
    try {
      return JSON.parse(localStorage.getItem(key(board)) || "{}") || {};
    } catch (e) {
      return {};
    }
  }
  function save(board, state) {
    try {
      localStorage.setItem(key(board), JSON.stringify(state));
    } catch (e) {
      /* no persistence available; the board still works this session */
    }
  }

  function cards(board) { return $$(":scope > [data-card]", board); }

  function persist(board) {
    save(board, {
      order: cards(board).map(function (c) { return c.dataset.card; }),
      collapsed: cards(board)
        .filter(function (c) { return c.classList.contains("is-collapsed"); })
        .map(function (c) { return c.dataset.card; })
    });
  }

  function setCollapsed(card, on) {
    card.classList.toggle("is-collapsed", on);
    var b = card.querySelector(".pn-fold");
    if (b) {
      b.setAttribute("aria-expanded", String(!on));
      b.title = on ? "Udvid" : "Minimer";
    }
  }

  function initBoard(board) {
    var state = load(board);
    var list = cards(board);
    if (!list.length) return;

    // Restore order first, so the saved arrangement is what the user
    // sees rather than a flash of the server order.
    if (state.order && state.order.length) {
      var byId = {};
      list.forEach(function (c) { byId[c.dataset.card] = c; });
      state.order.forEach(function (id) {
        if (byId[id]) board.append(byId[id]);
      });
      // Anything the saved order does not mention (a new panel) keeps
      // its position at the end rather than disappearing.
      list.forEach(function (c) {
        if (state.order.indexOf(c.dataset.card) < 0) board.append(c);
      });
    }

    cards(board).forEach(function (card) {
      var head = card.querySelector(".pn-h");
      if (!head) return;
      head.classList.add("pn-h-grab");

      // Controls are injected, not written into nine templates.
      var tools = document.createElement("span");
      tools.className = "pn-tools";

      var fold = document.createElement("button");
      fold.className = "pn-fold";
      fold.type = "button";
      fold.setAttribute("aria-expanded", "true");
      fold.title = "Minimer";
      fold.innerHTML = '<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
        + '<path d="M2 4.5 L6 8 L10 4.5" fill="none" stroke="currentColor" '
        + 'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      fold.addEventListener("click", function (e) {
        e.stopPropagation();
        setCollapsed(card, !card.classList.contains("is-collapsed"));
        persist(board);
      });

      var grip = document.createElement("span");
      grip.className = "pn-grip";
      grip.setAttribute("aria-hidden", "true");
      grip.textContent = "⋮⋮";

      tools.append(grip, fold);
      head.append(tools);

      if ((state.collapsed || []).indexOf(card.dataset.card) >= 0) {
        setCollapsed(card, true);
      }

      // Keyboard reorder, so the board is not mouse-only. The fold
      // button is already a real button; this moves the card.
      fold.addEventListener("keydown", function (e) {
        if (!e.altKey) return;
        var sibs = cards(board), i = sibs.indexOf(card);
        if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          if (i > 0) { board.insertBefore(card, sibs[i - 1]); e.preventDefault(); persist(board); fold.focus(); }
        } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          if (i < sibs.length - 1) { board.insertBefore(sibs[i + 1], card); e.preventDefault(); persist(board); fold.focus(); }
        }
      });
    });

    /* ---- pointer drag ------------------------------------------- */
    var dragging = null, startX = 0, startY = 0, armed = false;

    board.addEventListener("pointerdown", function (e) {
      var head = e.target.closest(".pn-h-grab");
      if (!head || !board.contains(head)) return;
      // Never steal a click from a control inside the header.
      if (e.target.closest("button, a, input, select, .seg")) return;
      var card = head.closest("[data-card]");
      if (!card) return;
      dragging = card; armed = false;
      startX = e.clientX; startY = e.clientY;
      try { board.setPointerCapture(e.pointerId); } catch (ignored) {}
    });

    board.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      // A few pixels of slop, so a click on the header is still a click.
      if (!armed) {
        if (Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) < 6) return;
        armed = true;
        dragging.classList.add("is-dragging");
        board.classList.add("is-sorting");
      }
      // Live reorder: swap with whichever sibling the pointer is over.
      // Guarded because a throwing handler would abandon the drag with
      // the card still marked as dragging.
      if (!document.elementFromPoint) return;
      var over = document.elementFromPoint(e.clientX, e.clientY);
      var target = over && over.closest && over.closest("[data-card]");
      if (!target || target === dragging || target.parentNode !== board) return;
      var r = target.getBoundingClientRect();
      var after = (e.clientX - r.left) > r.width / 2 || (e.clientY - r.top) > r.height / 2;
      board.insertBefore(dragging, after ? target.nextSibling : target);
    });

    function end(e) {
      if (!dragging) return;
      if (armed) {
        dragging.classList.remove("is-dragging");
        board.classList.remove("is-sorting");
        persist(board);
      }
      try { board.releasePointerCapture(e.pointerId); } catch (ignored) {}
      dragging = null; armed = false;
    }
    board.addEventListener("pointerup", end);
    board.addEventListener("pointercancel", end);
  }

  $$("[data-board]").forEach(initBoard);
})();
