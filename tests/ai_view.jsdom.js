/* Behaviour test for /ai, driven in jsdom.
 *
 *   npm install jsdom          # once, anywhere on the path
 *   docker compose up -d jytte # the test reads the real server
 *   node tests/ai_view.jsdom.js
 *
 * It runs the real page script against the real server HTML, so it
 * catches what a template render check cannot. It already earned its
 * keep: Esc closed the panel and then returned focus to the orb, whose
 * focus handler reopened it immediately.
 *
 * Asserted behaviour of the slide-in panel:
 *
 *   hover  -> opens, unpinned
 *   leave  -> closes after the grace period
 *   click  -> opens pinned, survives hovering something else
 *   Esc    -> closes a pinned panel
 *   X      -> closes a pinned panel
 *   flow   -> selecting rewrites the canvas and never navigates
 */
const http = require("http");

// jsdom is a test-only dependency and is deliberately NOT installed
// into this repo: it is a Python project and home-monitor/CLAUDE.md says
// to keep the frontend dependency light. Install it wherever you like
// and point NODE_PATH at it, or run this from that directory.
let JSDOM;
try {
  JSDOM = require("jsdom").JSDOM;
} catch (e) {
  console.error([
    "jsdom not found.",
    "  npm install jsdom            # anywhere, e.g. a scratch dir",
    "  NODE_PATH=<that>/node_modules node tests/ai_view.jsdom.js"
  ].join("\n"));
  process.exit(2);
}

function fetchText(path) {
  return new Promise((res, rej) => {
    http.get({ host: "localhost", port: 8080, path }, r => {
      let b = ""; r.on("data", c => (b += c)); r.on("end", () => res(b));
    }).on("error", rej);
  });
}

// The AI page moved under /legacy/* when the new dark UI shell took
// the canonical paths. One constant so the suite follows it.
const AI_PATH = process.env.AI_PATH || "/legacy/ai";

const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0;
function ok(cond, label) {
  console.log((cond ? "  PASS  " : "  FAIL  ") + label);
  if (!cond) fails++;
}

(async () => {
  const html = await fetchText(AI_PATH);
  const js = await fetchText("/static/ai.js");

  const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost:8080" + AI_PATH, pretendToBeVisual: true });
  const { window } = dom;
  const doc = window.document;

  // jsdom gaps, not page bugs: matchMedia and WAAPI are in every
  // browser this will run in. Stub them so their absence does not mask
  // a real error elsewhere.
  window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
  window.Element.prototype.animate = function () { return { set onfinish(_) {} }; };
  window.SVGElement.prototype.animate = window.Element.prototype.animate;

  const errors = [];
  window.addEventListener("error", e => errors.push(e.message));
  try {
    window.eval(js);
  } catch (e) {
    console.log("  FAIL  script threw: " + e.message + "\n" + e.stack);
    process.exit(1);
  }
  ok(errors.length === 0, "no runtime errors (" + (errors.join("; ") || "clean") + ")");

  const panel = doc.getElementById("ai-panel");
  const bodies = [...doc.querySelectorAll(".ai-body")];
  ok(bodies.length === 14, "14 agent bodies wired (" + bodies.length + ")");
  ok(panel.getAttribute("aria-hidden") === "true", "panel starts hidden");

  const PE = name => new window.PointerEvent(name, { bubbles: true });

  // ---- hover opens, unpinned
  bodies[0].dispatchEvent(PE("pointerenter"));
  ok(panel.classList.contains("is-open"), "hover opens the panel");
  ok(!panel.classList.contains("is-pinned"), "hover does not pin it");
  const title = doc.querySelector("#ai-panel-body h3");
  ok(title && title.textContent === bodies[0].dataset.agent,
     "panel shows the hovered agent (" + (title && title.textContent) + ")");
  ok(!!doc.querySelector("#ai-panel-body .ai-panel-desc").textContent.length,
     "description rendered in the panel, not under the button");
  ok(doc.querySelectorAll(".ai-body .ai-body-d").length === 0,
     "no description field left on the buttons");

  // ---- leaving closes it after the grace period
  bodies[0].dispatchEvent(PE("pointerleave"));
  ok(panel.classList.contains("is-open"), "still open inside the grace period");
  await sleep(220);
  ok(!panel.classList.contains("is-open"), "closes after pointer leaves");
  ok(panel.getAttribute("aria-hidden") === "true", "aria-hidden restored on close");

  // ---- moving between two orbs must not flash closed
  bodies[1].dispatchEvent(PE("pointerenter"));
  bodies[1].dispatchEvent(PE("pointerleave"));
  bodies[2].dispatchEvent(PE("pointerenter"));
  await sleep(220);
  ok(panel.classList.contains("is-open"), "orb to orb does not flash the panel closed");
  ok(doc.querySelector("#ai-panel-body h3").textContent === bodies[2].dataset.agent,
     "content follows the newly hovered orb");
  bodies[2].dispatchEvent(PE("pointerleave"));
  await sleep(220);

  // ---- click pins
  bodies[3].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  ok(panel.classList.contains("is-pinned"), "click pins the panel");
  ok(bodies[3].getAttribute("aria-pressed") === "true", "clicked body marked pressed");
  bodies[3].dispatchEvent(PE("pointerleave"));
  await sleep(240);
  ok(panel.classList.contains("is-open"), "pinned panel survives pointer leave");
  bodies[5].dispatchEvent(PE("pointerenter"));
  ok(doc.querySelector("#ai-panel-body h3").textContent === bodies[3].dataset.agent,
     "hovering elsewhere does not hijack a pinned panel");

  // ---- Esc closes a pinned panel
  doc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(!panel.classList.contains("is-open"), "Esc closes a pinned panel");
  ok(doc.querySelectorAll("[aria-pressed='true']").length === 0, "Esc clears the pressed state");

  // ---- X closes a pinned panel
  bodies[4].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  ok(panel.classList.contains("is-pinned"), "pinned again for the X test");
  doc.getElementById("ai-panel-x").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  ok(!panel.classList.contains("is-open"), "X closes the panel");

  // ---- clicking a pressed body again toggles it shut
  bodies[6].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  bodies[6].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  ok(!panel.classList.contains("is-open"), "second click on the same body closes it");

  // ---- orphan skill chips use the same panel
  const chip = doc.querySelector(".ai-chip[data-skill]");
  chip.dispatchEvent(PE("pointerenter"));
  ok(doc.querySelector("#ai-panel-body .ai-panel-eyebrow").textContent === "skill",
     "a skill chip renders as a skill in the same panel");
  chip.dispatchEvent(PE("pointerleave"));
  await sleep(220);

  // ---- workflow canvas
  const rail = [...doc.querySelectorAll(".ai-rail-item")];
  ok(rail.length === 10, "10 workflows in the rail (" + rail.length + ")");
  const stage = doc.getElementById("ai-stage");
  const cells0 = stage.querySelectorAll(".ai-cell").length;
  ok(cells0 === 9, "default flow drew 9 cells (" + cells0 + ")");
  const rows = new Set([...stage.querySelectorAll(".ai-cell")].map(c => c.style.top));
  ok(rows.size === 3, "default flow is 2D: 3 distinct rows (" + rows.size + ")");
  ok(stage.querySelectorAll(".ai-elabel").length === 5,
     "5 labelled branch edges (" + stage.querySelectorAll(".ai-elabel").length + ")");
  ok(stage.querySelector("svg path") !== null, "edges drawn as svg paths");
  ok(stage.querySelectorAll(".ai-drop.is-empty").length === 1,
     "the unscanned MCP lane is shown, not hidden");

  const before = window.location.href;
  rail.find(r => r.dataset.wf === "pr-complete").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  ok(doc.getElementById("ai-wf-title").textContent === "pr-complete", "selecting swaps the canvas");
  ok(stage.querySelectorAll(".ai-cell").length === 10, "pr-complete drew 10 cells");
  ok(window.location.href.indexOf("wf=pr-complete") > 0, "URL follows the selection");
  ok(window.location.pathname === AI_PATH, "no navigation away from /ai");

  // ---- a flow node opens the same panel
  const cell = stage.querySelector(".ai-cell");
  cell.dispatchEvent(PE("pointerenter"));
  ok(panel.classList.contains("is-open"), "a flow step opens the panel too");

  // ---- the pulse repeats rather than firing once
  //
  // jsdom reports every rect as zero, so geometry cannot be asserted
  // here. What CAN be asserted is that the timer exists, is bound to
  // the flow currently drawn, and does not keep firing at a detached
  // SVG after the flow is swapped. Counting animate() calls does that.
  let animCalls = 0;
  window.Element.prototype.animate = function () { animCalls++; return { set onfinish(_) {} }; };
  window.SVGElement.prototype.animate = window.Element.prototype.animate;

  // The timer idles while the flow view is hidden, so open the tab the
  // way a person would. Everything above drove the rail directly.
  doc.getElementById("tab-flow").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  animCalls = 0;
  await sleep(5400);
  ok(animCalls > 0, "pulse fires again on its own after 5s (" + animCalls + " dots)");

  // And it must stay idle when nobody is looking at it.
  doc.getElementById("tab-sky").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const idle = animCalls; animCalls = 0;
  await sleep(5400);
  ok(animCalls === 0, "pulse idles while the flow view is hidden");
  doc.getElementById("tab-flow").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  animCalls = idle;

  const firstRound = animCalls;
  animCalls = 0;
  await sleep(5400);
  ok(animCalls > 0 && animCalls === firstRound,
     "and keeps repeating at the same size (" + firstRound + " then " + animCalls + ")");

  // One timer for the page, so swapping flows must not double it up.
  rail.find(r => r.dataset.wf === "vault-lint").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const vaultSegs = animCalls;      // the immediate pulse on select
  animCalls = 0;
  await sleep(5400);
  ok(animCalls > 0 && animCalls < firstRound + vaultSegs,
     "swapping flow does not leave the old timer running (" + animCalls + ")");

  // ---- the panning sky
  const skyEl = doc.getElementById("ai-sky");
  const canvas = doc.getElementById("ai-sky-canvas");
  ok(skyEl && canvas, "sky viewport and canvas exist");
  ok(canvas.style.width === "1046px" && canvas.style.height === "670px",
     "canvas is a fixed size, not a reflowing grid (" + canvas.style.width + ")");
  ok([...doc.querySelectorAll(".ai-cluster")].every(c => c.style.left && c.style.top),
     "every cluster is placed at an explicit point on the canvas");

  // Drag moves it; jsdom gives zero-size rects, so the clamp pins the
  // canvas rather than letting it wander. Assert the handler runs and
  // writes a transform at all, which is what a zero-rect clamp allows.
  skyEl.dispatchEvent(new window.PointerEvent("pointerdown", { bubbles: true, clientX: 500, clientY: 300, pointerId: 1 }));
  skyEl.dispatchEvent(new window.PointerEvent("pointermove", { bubbles: true, clientX: 380, clientY: 260, pointerId: 1 }));
  ok(/translate\(/.test(canvas.style.transform),
     "dragging the sky writes a transform (" + canvas.style.transform + ")");
  skyEl.dispatchEvent(new window.PointerEvent("pointerup", { bubbles: true, clientX: 380, clientY: 260, pointerId: 1 }));

  // A pointerdown that starts on an agent must not begin a drag, or
  // clicking an agent would pan the field out from under the cursor.
  const beforeDrag = canvas.style.transform;
  bodies[0].dispatchEvent(new window.PointerEvent("pointerdown", { bubbles: true, clientX: 200, clientY: 200, pointerId: 2 }));
  skyEl.dispatchEvent(new window.PointerEvent("pointermove", { bubbles: true, clientX: 60, clientY: 90, pointerId: 2 }));
  ok(canvas.style.transform === beforeDrag, "pointerdown on an agent does not drag the field");

  // Leaving the field closes an unpinned panel.
  panel.classList.contains("is-open") || bodies[1].dispatchEvent(PE("pointerenter"));
  skyEl.dispatchEvent(PE("pointerleave"));
  await sleep(220);
  ok(!panel.classList.contains("is-open"), "leaving the sky closes an unpinned panel");


/* ---- scope summary and the ledger ------------------------------- */
  const sumCards = [...doc.querySelectorAll(".ai-sum-card")];
  ok(sumCards.length === 2, "two summary cards, agents and skills (" + sumCards.length + ")");

  const readCard = i => Object.fromEntries(
    [...sumCards[i].querySelectorAll(".ai-sum-grid > div")]
      .map(d => [d.querySelector("dt").textContent.trim(), +d.querySelector("dd").textContent]));
  const A = readCard(0), S = readCard(1);
  ok(A["global"] + A["projekt"] + (A["begge steder"] || 0) === 14,
     "agent scopes add up to the total (" + JSON.stringify(A) + ")");
  ok(S["global"] + S["projekt"] + (S["begge steder"] || 0) === 52,
     "skill scopes add up to the total (" + JSON.stringify(S) + ")");
  ok(S["begge steder"] === 3, "3 skills live globally AND in a project (" + S["begge steder"] + ")");
  ok(S["heraf identiske"] + S["skal flettes"] === S["findes flere steder"],
     "identical duplicates plus merge candidates equal all duplicates");

  const ledgerRows = [...doc.querySelectorAll(".ai-table tbody tr")];
  ok(ledgerRows.length === 66, "ledger lists all 66 capabilities (" + ledgerRows.length + ")");
  ok(ledgerRows.filter(r => r.dataset.kind === "agent").length === 14, "14 agent rows");
  ok(ledgerRows.filter(r => r.dataset.kind === "skill").length === 52, "52 skill rows");

  // A skill has no runs column, because nothing logs skill invocations.
  // Empty is the honest value; zero would be a claim.
  const skillRow = ledgerRows.find(r => r.dataset.kind === "skill");
  ok(/ingen log for skills/.test(skillRow.innerHTML),
     "a skill row says there is no skill log rather than showing 0");

  // Attempt bars exist only for agents that actually ran.
  const bars = [...doc.querySelectorAll(".ai-att")];
  ok(bars.length === 11, "11 agents have attempt bars, one per agent with runs (" + bars.length + ")");
  const widest = bars[0].querySelectorAll("i");
  ok(widest.length >= 1 && widest[0].className === "t-ok",
     "the first segment of every bar is first-time-right");

  // Filters
  const visible = () => ledgerRows.filter(r => !r.hidden).length;
  const click = f => doc.querySelector('.ai-filters button[data-f="' + f + '"]')
                        .dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  click("agent");  ok(visible() === 14, "filter agents shows 14 (" + visible() + ")");
  click("skill");  ok(visible() === 52, "filter skills shows 52 (" + visible() + ")");
  click("global"); ok(visible() === 24, "filter global shows 24 (" + visible() + ")");
  click("project");ok(visible() === 39, "filter projekt shows 39, excluding both (" + visible() + ")");
  click("both");   ok(visible() === 3,  "filter begge steder shows 3 (" + visible() + ")");
  click("merge");  ok(visible() === 13, "filter flet shows 13 merge candidates (" + visible() + ")");
  click("cold");   ok(visible() === 3,  "filter aldrig brugt shows 3 (" + visible() + ")");
  click("all");    ok(visible() === 66, "filter alle restores every row (" + visible() + ")");

  // The ledger and the summary chips open the same slide-in panel.
  doc.querySelector(".ai-ledger-n").dispatchEvent(PE("pointerenter"));
  ok(panel.classList.contains("is-open"), "a ledger name opens the detail panel");
  doc.querySelector(".ai-ledger-n").dispatchEvent(PE("pointerleave"));
  await sleep(220);

  const mergeChip = doc.querySelector('.ai-sum-note .ai-chip[data-agent]');
  mergeChip.dispatchEvent(PE("pointerenter"));
  ok(doc.querySelector("#ai-panel-body h3").textContent === mergeChip.dataset.agent,
     "a merge-candidate chip opens that agent (" + mergeChip.dataset.agent + ")");
  mergeChip.dispatchEvent(PE("pointerleave"));
  await sleep(220);

  // ---- the honesty notes must be on the page, not just in my head
  const foots = doc.querySelector(".ai-foots").textContent;
  ok(/ikke en succesrate/.test(foots), "the page says attempts is not a success rate");
  ok(/ingen log over\s+skill-kald/.test(foots.replace(/\s+/g, " ")),
     "the page says there is no skill invocation log");
  ok(/uden en definitionsfil/.test(foots), "the page reports runs with no definition file");

  /* ---- the reveal geometry, with injected rects -------------------
   *
   * This is the whole point of the panning field, and jsdom reports
   * every rect as 0x0, so none of the assertions above touch it. Feed
   * the real code fake geometry instead and check the arithmetic:
   *
   *   viewport   left 40  right 1400  top 200  bottom 900
   *   window     1440 wide, panel 384 wide -> panel starts at 1056
   *   so the rightmost usable pixel is 1056 - 26 (gap) = 1030
   */
  Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
  Object.defineProperty(panel, "offsetWidth", { value: 384, configurable: true });
  const VP = { left: 40, right: 1400, top: 200, bottom: 900, width: 1360, height: 700 };
  skyEl.getBoundingClientRect = () => VP;
  Object.defineProperty(canvas, "offsetWidth", { value: 1046, configurable: true });
  Object.defineProperty(canvas, "offsetHeight", { value: 670, configurable: true });

  const panOf = () => {
    const m = /translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)/.exec(canvas.style.transform);
    return m ? [parseFloat(m[1]), parseFloat(m[2])] : [0, 0];
  };
  function hoverWithRect(body, rect) {
    // Reset to a known corner first. Without this each assertion
    // starts from wherever the previous one left the field, and a
    // clamp hit earlier silently changes the expected delta later.
    dragBy(5000, 5000);
    body.getBoundingClientRect = () => rect;
    const before = panOf();
    body.dispatchEvent(PE("pointerenter"));
    const after = panOf();
    body.dispatchEvent(PE("pointerleave"));
    return [after[0] - before[0], after[1] - before[1]];
  }
  function dragBy(dx, dy) {
    skyEl.dispatchEvent(new window.PointerEvent("pointerdown", { bubbles: true, clientX: 700, clientY: 500, pointerId: 9 }));
    skyEl.dispatchEvent(new window.PointerEvent("pointermove", { bubbles: true, clientX: 700 + dx, clientY: 500 + dy, pointerId: 9 }));
    skyEl.dispatchEvent(new window.PointerEvent("pointerup", { bubbles: true, clientX: 700 + dx, clientY: 500 + dy, pointerId: 9 }));
  }

  // Already clear of the panel: must not move at all. An agent that
  // runs away from the cursor is worse than one sitting still.
  let d = hoverWithRect(bodies[8], { left: 300, right: 404, top: 400, bottom: 480 });
  ok(d[0] === 0 && d[1] === 0, "an agent already clear of the panel does not move (" + d + ")");

  // Under the panel: pans left by exactly enough to clear it.
  d = hoverWithRect(bodies[9], { left: 980, right: 1084, top: 400, bottom: 480 });
  ok(d[0] === -54 && d[1] === 0,
     "an occluded agent pans left exactly 54px to clear the panel (" + d + ")");

  // Deeper under the panel: further, but still only as far as needed.
  d = hoverWithRect(bodies[10], { left: 1150, right: 1254, top: 400, bottom: 480 });
  ok(d[0] === -224 && d[1] === 0,
     "a fully hidden agent pans 224px, no further (" + d + ")");

  // Below the fold: pans up, not sideways.
  d = hoverWithRect(bodies[11], { left: 300, right: 404, top: 950, bottom: 1030 });
  ok(d[0] === 0 && d[1] === -156,
     "an agent past the bottom edge pans up only (" + d + ")");

  // The clamp must stop a drag wandering off into empty space.
  // usable width 1016 against a 1046 canvas, slack 150 -> x in [-180, 150].
  dragBy(5000, 0);
  ok(panOf()[0] === 150, "dragging right stops at the slack limit (" + panOf()[0] + ")");
  dragBy(-5000, 0);
  ok(panOf()[0] === -180, "dragging left stops at the slack limit (" + panOf()[0] + ")");
  dragBy(0, -5000);
  ok(panOf()[1] === -120, "dragging up stops at the slack limit (" + panOf()[1] + ")");

  console.log(fails ? "\n" + fails + " FAILED" : "\nall assertions passed");
  process.exit(fails ? 1 : 0);
})();
