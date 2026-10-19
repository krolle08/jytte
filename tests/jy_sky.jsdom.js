/* Behaviour test for the constellation field.
 *
 *   npm install jsdom
 *   docker compose up -d jytte
 *   NODE_PATH=<that>/node_modules node tests/jy_sky.jsdom.js
 *
 * jsdom has no layout, so every rect is 0x0 and the clamp pins the
 * field. Geometry is therefore injected, the same way
 * tests/ai_view.jsdom.js does it, so the pan and zoom arithmetic is
 * actually exercised rather than skipped.
 */
const http = require("http");

let JSDOM;
try {
  JSDOM = require("jsdom").JSDOM;
} catch (e) {
  console.error([
    "jsdom not found.",
    "  npm install jsdom            # anywhere, e.g. a scratch dir",
    "  NODE_PATH=<that>/node_modules node tests/jy_sky.jsdom.js"
  ].join("\n"));
  process.exit(2);
}

const get = p => new Promise((res, rej) => {
  http.get({ host: "localhost", port: 8080, path: p }, r => {
    let b = ""; r.on("data", c => (b += c)); r.on("end", () => res(b));
  }).on("error", rej);
});

const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0;
const ok = (c, l) => { console.log((c ? "  PASS  " : "  FAIL  ") + l); if (!c) fails++; };

// Viewport 1100x640 at the page origin; canvas is the real 1440x1020.
const VP = { left: 0, top: 0, right: 1100, bottom: 640, width: 1100, height: 640 };

(async () => {
  const html = await get("/constellation");
  const js = await get("/static/jy_ai.js");
  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    url: "http://localhost:8080/constellation",
    pretendToBeVisual: true
  });
  const w = dom.window, doc = w.document;
  w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
  w.Element.prototype.animate = function () { return { set onfinish(_) {} }; };
  doc.elementFromPoint = () => null;
  Object.defineProperty(w, "innerWidth", { value: 1440, configurable: true });

  const sky = doc.getElementById("jy-sky");
  const inner = doc.getElementById("jy-sky-inner");
  sky.getBoundingClientRect = () => VP;
  Object.defineProperty(inner, "offsetWidth", { value: 1440, configurable: true });
  Object.defineProperty(inner, "offsetHeight", { value: 1020, configurable: true });
  const panel = doc.getElementById("jp");
  Object.defineProperty(panel, "offsetWidth", { value: 340, configurable: true });

  w.eval(js);

  const tf = () => {
    const m = /translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)\s*scale\(([\d.]+)\)/
      .exec(inner.style.transform);
    return m ? { x: +m[1], y: +m[2], s: +m[3] } : null;
  };

  // ---- opens fitted, not parked on an empty corner
  let t0 = tf();
  ok(!!t0, "transform is one translate + scale (" + inner.style.transform + ")");
  ok(Math.abs(t0.s - Math.min((1100 - 32) / 1440, (640 - 32) / 1020)) < 0.01,
     "opens fitted to the viewport (scale " + t0.s.toFixed(3) + ")");
  ok(t0.x > 0 && t0.y > 0, "and centred, not at the top-left corner");

  const PE = (n, o) => new w.PointerEvent(n, Object.assign({ bubbles: true, pointerId: 1 }, o));

  // ---- drag pans
  sky.dispatchEvent(PE("pointerdown", { clientX: 500, clientY: 300 }));
  sky.dispatchEvent(PE("pointermove", { clientX: 420, clientY: 260 }));
  let t1 = tf();
  ok(t1.x === t0.x - 80 && t1.y === t0.y - 40,
     "drag moves the field by exactly the pointer delta (" + (t1.x - t0.x) + "," + (t1.y - t0.y) + ")");
  ok(t1.s === t0.s, "dragging does not change the zoom");
  sky.dispatchEvent(PE("pointerup", {}));
  ok(!sky.classList.contains("is-dragging"), "pointerup ends the drag");

  // ---- a pointerdown on a node must not pan the field
  const before = tf();
  const agent = doc.querySelector(".jy-agent");
  agent.dispatchEvent(PE("pointerdown", { clientX: 300, clientY: 300 }));
  sky.dispatchEvent(PE("pointermove", { clientX: 100, clientY: 100 }));
  ok(tf().x === before.x, "pointerdown on an agent does not drag the field");
  sky.dispatchEvent(PE("pointerup", {}));

  // ---- wheel zooms about the pointer: the canvas point under the
  // cursor must be the same before and after, which is the whole
  // reason for doing the arithmetic rather than just scaling.
  //
  // Zoom in past fit first. At fit the field is SMALLER than the
  // viewport, so the clamp is active and holding the point fixed is
  // impossible - the same reason a map cannot keep a point fixed while
  // you push against its edge. The property only holds with room to
  // move, which is where it matters.
  const atCanvas = (t, cx, cy) => [(cx - t.x) / t.s, (cy - t.y) / t.s];
  const PX = 550, PY = 320;
  for (let i = 0; i < 6; i++) {
    sky.dispatchEvent(new w.WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: -100, clientX: PX, clientY: PY }));
  }
  ok(tf().s * 1440 > VP.width, "zoomed past fit, so the clamp is not holding it (" + Math.round(tf().s * 1440) + "px wide)");
  let pre = tf(), preCanvas = atCanvas(pre, PX, PY);
  sky.dispatchEvent(new w.WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: -100, clientX: PX, clientY: PY }));
  let post = tf(), postCanvas = atCanvas(post, PX, PY);
  ok(post.s > pre.s, "wheel up zooms in (" + pre.s.toFixed(3) + " -> " + post.s.toFixed(3) + ")");
  ok(Math.abs(preCanvas[0] - postCanvas[0]) < 0.5 && Math.abs(preCanvas[1] - postCanvas[1]) < 0.5,
     "the point under the cursor stays under the cursor");

  sky.dispatchEvent(new w.WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: 100, clientX: PX, clientY: PY }));
  ok(Math.abs(tf().s - pre.s) < 0.02, "wheel down returns to the previous zoom");
  doc.getElementById("jy-zfit").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

  // ---- zoom is bounded
  for (let i = 0; i < 40; i++) {
    sky.dispatchEvent(new w.WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: -100, clientX: PX, clientY: PY }));
  }
  ok(tf().s <= 2.2 + 1e-6, "zoom stops at the max (" + tf().s.toFixed(2) + ")");
  for (let i = 0; i < 60; i++) {
    sky.dispatchEvent(new w.WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: 100, clientX: PX, clientY: PY }));
  }
  ok(tf().s >= 0.35 - 1e-6, "zoom stops at the min (" + tf().s.toFixed(2) + ")");

  // ---- fit and the buttons
  doc.getElementById("jy-zfit").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(Math.abs(tf().s - t0.s) < 0.01, "fit returns to the opening zoom");
  doc.getElementById("jy-zin").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(tf().s > t0.s, "the + button zooms in");
  doc.getElementById("jy-zout").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(Math.abs(tf().s - t0.s) < 0.01, "the - button comes back");
  sky.dispatchEvent(new w.MouseEvent("dblclick", { bubbles: true }));
  ok(Math.abs(tf().s - t0.s) < 0.01, "double-click fits");

  // ---- keyboard pans and zooms
  const kb = (key, mod) => sky.dispatchEvent(new w.KeyboardEvent("keydown",
    Object.assign({ key: key, bubbles: true, cancelable: true }, mod || {})));
  // Zoom in first so there is room to pan, otherwise the clamp caps
  // every step and the assertions would only measure the clamp.
  for (let i = 0; i < 6; i++) {
    sky.dispatchEvent(new w.WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: -100, clientX: 550, clientY: 320 }));
  }
  let kpre = tf();
  kb("ArrowRight");
  ok(tf().x === kpre.x - 80, "arrow right pans 80px (" + (tf().x - kpre.x) + ")");
  kb("ArrowLeft");
  ok(tf().x === kpre.x, "arrow left pans back");
  kb("ArrowRight", { shiftKey: true });
  ok(tf().x === kpre.x - 240, "shift+arrow pans 240px (" + (tf().x - kpre.x) + ")");
  kb("ArrowLeft", { shiftKey: true });
  // Push hard against the edge: it must stop, not run off.
  for (let i = 0; i < 40; i++) kb("ArrowRight", { shiftKey: true });
  const edge = tf().x;
  kb("ArrowRight", { shiftKey: true });
  ok(tf().x === edge, "panning stops at the edge instead of running off");
  kb("0");
  ok(Math.abs(tf().s - t0.s) < 0.01, "0 fits");

  // ---- focus: hovering an agent dims the rest and names its skills
  const agents = [].slice.call(doc.querySelectorAll(".jy-agent"));
  const skills = [].slice.call(doc.querySelectorAll(".jy-skill"));
  ok(agents.length === 14, "14 agents on the field (" + agents.length + ")");
  ok(skills.length === 44, "44 skills in orbit (" + skills.length + ")");
  ok(doc.querySelectorAll(".jy-sector").length === 5, "5 category sectors");

  const owner = skills.find(s => s.dataset.owner).dataset.owner;
  const target = agents.find(a => a.dataset.agent === owner);
  target.dispatchEvent(PE("pointerenter", {}));
  ok(sky.classList.contains("is-focused"), "hovering an agent focuses the field");
  ok(target.classList.contains("is-lit"), "the hovered agent is lit");
  ok(agents.filter(a => a.classList.contains("is-dim")).length === 13,
     "the other 13 agents dim");
  const mine = skills.filter(s => s.dataset.owner === owner);
  ok(mine.every(s => s.classList.contains("is-lit")),
     "that agent's own skills light up (" + mine.length + ")");
  ok(skills.filter(s => s.dataset.owner !== owner).every(s => s.classList.contains("is-dim")),
     "every other skill dims");
  const litEdges = [].slice.call(doc.querySelectorAll(".jy-edge.is-lit"));
  ok(litEdges.length === 1 + mine.length,
     "its hub edge and skill edges light (" + litEdges.length + ")");

  // ---- hovering a shared skill lights every agent that declares it
  const shared = skills.find(s => s.classList.contains("is-shared"));
  if (shared) {
    shared.dispatchEvent(PE("pointerenter", {}));
    const lit = agents.filter(a => a.classList.contains("is-lit"));
    ok(lit.length >= 2, "a shared skill lights every agent that declares it (" + lit.length + ")");
  }

  // ---- leaving the field clears the focus
  sky.dispatchEvent(PE("pointerleave", {}));
  await sleep(10);
  ok(!sky.classList.contains("is-focused"), "leaving the field clears the focus");

  // ---- the panel still works here, and the field pans clear of it
  const a2 = agents[0];
  a2.getBoundingClientRect = () => ({ left: 980, right: 1084, top: 300, bottom: 380 });
  const px = tf().x;
  a2.dispatchEvent(PE("pointerenter", {}));
  ok(panel.classList.contains("is-open"), "hovering an agent opens the panel");
  ok(tf().x < px, "and the field pans left to clear it (" + (tf().x - px).toFixed(0) + "px)");

  console.log(fails ? "\n" + fails + " FAILED" : "\nall assertions passed");
  process.exit(fails ? 1 : 0);
})();
