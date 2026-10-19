/* POC: WoW Forever patch notes. Three small jobs, none of them load
   content: every panel is rendered server-side, so the page reads in
   full with this file missing.

   1. Class tabs only toggle `hidden` on panels that are already there.
   2. Countdowns recount on the client, so a tab left open overnight
      does not keep yesterday's number.
   3. The hero embers. Off under prefers-reduced-motion. */
(() => {
  const root = document.querySelector(".wf");
  if (!root) return;

  // 1. class tabs
  const tabs = [...root.querySelectorAll(".wf-cls button")];
  const show = name => {
    tabs.forEach(b => b.setAttribute("aria-selected", String(b.dataset.c === name)));
    root.querySelectorAll(".wf-book").forEach(p => { p.hidden = p.dataset.c !== name; });
    try { localStorage.setItem("wf-class", name); } catch (e) {}
  };
  tabs.forEach(b => b.addEventListener("click", () => show(b.dataset.c)));
  let saved = null;
  try { saved = localStorage.getItem("wf-class"); } catch (e) {}
  if (saved && tabs.some(b => b.dataset.c === saved)) show(saved);

  // 2. countdowns
  const today = new Date(); today.setHours(0, 0, 0, 0);
  root.querySelectorAll("[data-until]").forEach(el => {
    const d = new Date(el.dataset.until + "T00:00:00");
    el.textContent = Math.max(0, Math.round((d - today) / 864e5));
  });

  // 3. embers
  const cv = root.querySelector(".wf-hero canvas");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W = 0, H = 0;
  const P = [];
  const size = () => {
    const r = cv.getBoundingClientRect(), d = devicePixelRatio || 1;
    W = r.width; H = r.height; cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0);
  };
  const spawn = y => ({x: Math.random() * W, y: y ?? H + 10, r: Math.random() * 2.2 + .6, v: Math.random() * .6 + .25,
                       w: Math.random() * 6.28, hue: Math.random() < .7 ? 38 : 232, a: Math.random() * .6 + .3});
  size(); addEventListener("resize", size);
  for (let i = 0; i < 90; i++) P.push(spawn(Math.random() * H));
  const draw = () => {
    ctx.clearRect(0, 0, W, H);
    for (const p of P) {
      p.y -= p.v; p.w += .02; p.x += Math.sin(p.w) * .35;
      if (p.y < -10) Object.assign(p, spawn());
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 5);
      g.addColorStop(0, `hsla(${p.hue},100%,70%,${p.a})`); g.addColorStop(1, `hsla(${p.hue},100%,50%,0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 5, 0, 6.29); ctx.fill();
    }
    if (!still) requestAnimationFrame(draw);
  };
  draw();
})();
