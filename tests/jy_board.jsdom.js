/* Behaviour test for the panel board.
 *
 *   npm install jsdom
 *   docker compose up -d jytte
 *   NODE_PATH=<that>/node_modules node tests/jy_board.jsdom.js
 *
 * Covers what the screenshot complaint was about: panels sitting two
 * per row instead of one full-width column, and each one collapsible
 * and movable with the arrangement remembered.
 */
const http = require("http");

let JSDOM;
try {
  JSDOM = require("jsdom").JSDOM;
} catch (e) {
  console.error([
    "jsdom not found.",
    "  npm install jsdom            # anywhere, e.g. a scratch dir",
    "  NODE_PATH=<that>/node_modules node tests/jy_board.jsdom.js"
  ].join("\n"));
  process.exit(2);
}

const get = p => new Promise((res, rej) => {
  http.get({ host: "localhost", port: 8080, path: p }, r => {
    let b = ""; r.on("data", c => (b += c)); r.on("end", () => res(b));
  }).on("error", rej);
});

let fails = 0;
const ok = (c, l) => { console.log((c ? "  PASS  " : "  FAIL  ") + l); if (!c) fails++; };

async function boot(path, js) {
  const html = await get(path);
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost:8080" + path, pretendToBeVisual: true });
  const w = dom.window;
  w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
  w.Element.prototype.animate = function () { return { set onfinish(_) {} }; };
  // jsdom defines localStorage as a read-only accessor, so a plain
  // assignment is silently dropped. defineProperty replaces it, and one
  // shared stub lets the second boot see what the first saved - which
  // is the whole point of the persistence assertions.
  Object.defineProperty(w, "localStorage", { value: boot.store, configurable: true });
  // Reordering reads the pointer position; jsdom has no layout.
  if (!w.document.elementFromPoint) w.document.elementFromPoint = () => null;
  w.eval(js);
  return w;
}

(async () => {
  const js = await get("/static/jy_board.js");

  // Shared, so "remembers across a reload" is actually testable.
  const mem = {};
  boot.store = {
    getItem: k => (k in mem ? mem[k] : null),
    setItem: (k, v) => { mem[k] = String(v); },
    removeItem: k => { delete mem[k]; }
  };

  let w = await boot("/devops", js);
  let doc = w.document;
  const board = doc.querySelector('[data-board="devops"]');
  ok(!!board, "devops has a board");
  const ids = () => [].slice.call(board.children).map(c => c.dataset.card);
  ok(ids().join(",") === "workitems,prs,pipelines", "three cards in source order (" + ids() + ")");

  // ---- controls are injected, not written into each template
  ok(board.querySelectorAll(".pn-fold").length === 3, "every card got a collapse button");
  ok(board.querySelectorAll(".pn-grip").length === 3, "every card got a grip");
  ok(board.querySelectorAll(".pn-h-grab").length === 3, "every header is a handle");

  // ---- collapse
  const pipes = board.querySelector('[data-card="pipelines"]');
  const fold = pipes.querySelector(".pn-fold");
  ok(fold.getAttribute("aria-expanded") === "true", "starts expanded");
  fold.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(pipes.classList.contains("is-collapsed"), "click collapses the card");
  ok(fold.getAttribute("aria-expanded") === "false", "aria-expanded follows");
  fold.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(!pipes.classList.contains("is-collapsed"), "click again expands it");

  // ---- keyboard reorder, so the board is not mouse-only
  const first = board.querySelector('[data-card="workitems"] .pn-fold');
  first.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowRight", altKey: true, bubbles: true }));
  ok(ids().join(",") === "prs,workitems,pipelines", "alt+right moves a card later (" + ids() + ")");
  first.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowLeft", altKey: true, bubbles: true }));
  ok(ids().join(",") === "workitems,prs,pipelines", "alt+left moves it back (" + ids() + ")");

  // ---- a plain click on a control inside the header must not drag
  const PD = (t, x, y) => {
    const e = new w.PointerEvent("pointerdown", { bubbles: true, clientX: x, clientY: y, pointerId: 3 });
    t.dispatchEvent(e);
  };
  PD(fold, 10, 10);
  board.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 400, clientY: 400, pointerId: 3 }));
  ok(!board.classList.contains("is-sorting"), "pointerdown on the fold button does not start a drag");
  board.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, pointerId: 3 }));

  // ---- drag from the header does, and only past the slop threshold
  const head = board.querySelector('[data-card="workitems"] .pn-h');
  PD(head, 100, 100);
  board.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 102, clientY: 101, pointerId: 3 }));
  ok(!board.classList.contains("is-sorting"), "2px of movement is still a click, not a drag");
  board.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 140, clientY: 130, pointerId: 3 }));
  ok(board.classList.contains("is-sorting"), "past the slop it becomes a drag");
  board.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, pointerId: 3 }));
  ok(!board.classList.contains("is-sorting"), "pointerup ends the drag");

  // ---- persistence: collapse one, move one, reload, both survive
  board.querySelector('[data-card="prs"] .pn-fold')
       .dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  board.querySelector('[data-card="workitems"] .pn-fold')
       .dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowRight", altKey: true, bubbles: true }));
  const want = ids().join(",");
  ok(Object.keys(mem).length === 1, "one localStorage key per board (" + Object.keys(mem) + ")");

  w = await boot("/devops", js);
  doc = w.document;
  const b2 = doc.querySelector('[data-board="devops"]');
  const ids2 = [].slice.call(b2.children).map(c => c.dataset.card).join(",");
  ok(ids2 === want, "order survives a reload (" + ids2 + " vs " + want + ")");
  ok(b2.querySelector('[data-card="prs"]').classList.contains("is-collapsed"),
     "collapsed state survives a reload");

  // ---- a board whose saved order is stale must not lose a panel
  mem[Object.keys(mem)[0]] = JSON.stringify({ order: ["pipelines"], collapsed: [] });
  w = await boot("/devops", js);
  const b3 = w.document.querySelector('[data-board="devops"]');
  const ids3 = [].slice.call(b3.children).map(c => c.dataset.card);
  ok(ids3.length === 3, "a partial saved order still renders every card (" + ids3 + ")");
  ok(ids3[0] === "pipelines", "the saved card leads (" + ids3[0] + ")");

  // ---- storage that throws must not take the board down
  boot.store = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
    removeItem() {}
  };
  w = await boot("/devops", js);
  const b4 = w.document.querySelector('[data-board="devops"]');
  ok(b4.querySelectorAll(".pn-fold").length === 3,
     "board still works when localStorage throws");

  // ---- other boards
  boot.store = { getItem: () => null, setItem() {}, removeItem() {} };
  for (const [path, key, n] of [["/", "home", 3], ["/ai", "ai", 3], ["/budget", "budget", 2]]) {
    const ww = await boot(path, js);
    const bb = ww.document.querySelector('[data-board="' + key + '"]');
    ok(bb && bb.querySelectorAll(".pn-fold").length === n,
       path + " board has " + n + " collapsible cards");
  }

  // ---- the row fix: no column eats the slack any more
  const dv = await get("/devops");
  ok(!/120px auto auto/.test(dv), "the stranded 120px column is gone");
  ok(/class="row row-grp"/.test(dv), "pipeline rows use the grouped grid");
  ok((dv.match(/class="row-meta"/g) || []).length >= 3, "meta is a right-aligned cluster");

  console.log(fails ? "\n" + fails + " FAILED" : "\nall assertions passed");
  process.exit(fails ? 1 : 0);
})();
