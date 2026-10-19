// Data loader. Added by the step 2 split.
//
// Calls /api/<name> and falls back to mock/<name>.json when the call
// fails or ?mock=1 is set. The rest of this file is the PoC behaviour
// verbatim and does not know which source it got.
const MOCK_ONLY = new URLSearchParams(location.search).has("mock");

async function load(name) {
  if (!MOCK_ONLY) {
    try {
      const r = await fetch("/api/" + name, { headers: { accept: "application/json" } });
      if (r.ok) return await r.json();
    } catch (e) {
      // fall through to mock
    }
  }
  const r = await fetch("mock/" + name + ".json");
  if (!r.ok) throw new Error("no data for " + name);
  return await r.json();
}

// The PoC read these as module-scope constants, so keep the same names
// and fill them before anything renders.
let D = {}, AGENTS = {}, SKILLS = {}, THEMES = [], WF = {};

async function bootData() {
  const [cal, mail, tasks, devops, ai] = await Promise.all(
    ["calendar", "mail", "tasks", "devops", "ai"].map(load)
  );
  D = Object.assign({}, devops, { cal, mail, tasks });
  AGENTS = ai.agents || {};
  SKILLS = ai.skills || {};
  THEMES = ai.themes || [];
  WF = ai.workflows || {};
}

/* ---------- MOCK DATA ---------- */
/* AI architecture: registries + workflows. kinds: trigger, agent, skill, tool, gate */
function chain(a) { var o = []; for (var i = 0; i < a.length - 1; i++) o.push([a[i], a[i + 1]]); return o; }
var KC = { trigger: "var(--k-trigger)", agent: "var(--k-agent)", skill: "var(--k-skill)", tool: "var(--k-tool)", gate: "var(--k-gate)" };

/* ---------- STATE ---------- */
var S = { view: "today", theme: "all", wf: "morning-brief", ref: null, node: null, zoom: null, mailCat: "Important", kw: ["Lars", "Dagrofa"], cfgOpen: false };
var $ = function (s) { return document.querySelector(s); };

function usedIn(type, id) {
  return Object.keys(WF).filter(function (k) {
    return WF[k].nodes.some(function (n) {
      if (!n.r) return false;
      if (n.r === id) return true;
      return type === "skill" && n.k === "agent" && AGENTS[n.r].skills.indexOf(id) > -1;
    });
  });
}
function projOf(wid) {
  for (var i = 0; i < THEMES.length; i++) for (var j = 0; j < THEMES[i].projects.length; j++)
    if (THEMES[i].projects[j].wfs.indexOf(wid) > -1) return { t: THEMES[i].name, p: THEMES[i].projects[j].name };
}

/* ---------- TODAY ---------- */
function esc(x) { return String(x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
function plural(n, w) { return n + " " + w + (n === 1 ? "" : "s"); }
function loadPrefs() {
  try { var r = JSON.parse(localStorage.getItem("hm.mail")); if (r) { if (typeof r.cat === "string") S.mailCat = r.cat; if (Array.isArray(r.kw)) S.kw = r.kw; } } catch (e) {}
}
function savePrefs() { try { localStorage.setItem("hm.mail", JSON.stringify({ cat: S.mailCat, kw: S.kw })); } catch (e) {} }

function importance(m) {
  var cat = (S.mailCat || "").trim().toLowerCase();
  if (cat && m.cats.some(function (c) { return c.toLowerCase() === cat; })) return "Outlook tag";
  var hay = (m.from + " " + m.subj).toLowerCase();
  for (var i = 0; i < S.kw.length; i++) if (hay.indexOf(S.kw[i].toLowerCase()) > -1) return "Keyword: " + S.kw[i];
  return "";
}
function groupMails() {
  var all = D.mails.map(function (m) { return { m: m, why: importance(m) }; });
  return { imp: all.filter(function (x) { return x.why; }), rest: all.filter(function (x) { return !x.why; }) };
}
function openTarget(o) { return o.teams ? { href: o.teams, label: "Join in Teams", cls: "teams" } : { href: o.web, label: "Open in Outlook", cls: "" }; }
function linkRow(o, unread, inner, tag) {
  var t = openTarget(o);
  return '<a class="row' + (unread ? ' unread' : '') + '" href="' + esc(t.href) + '" target="_blank" rel="noopener">' + inner + '<span class="rt">' + (tag || '') + '<span class="open ' + t.cls + '">' + t.label + ' &#8599;</span></span></a>';
}
function mailRow(x) {
  var m = x.m;
  return linkRow(m, m.unread, '<span class="time">' + m.t + '</span><div class="main"><div class="t">' + esc(m.subj) + '</div><div class="s">' + esc(m.from) +
    (x.why ? ' · <span class="acc">' + esc(x.why) + '</span>' : '') + '</div></div>', '<span class="tag">' + esc(m.tag) + '</span>');
}
function mailBody(g) {
  var h = '';
  if (g.imp.length) h += '<div class="mhead">Important · ' + g.imp.length + '</div>' + g.imp.map(mailRow).join('');
  h += '<div class="mhead">Other · ' + g.rest.length + '</div>' + g.rest.map(mailRow).join('');
  h += '<details class="cfg" id="cfg"' + (S.cfgOpen ? ' open' : '') + '><summary>Importance rules</summary>' +
    '<label for="mail-cat">Outlook category that marks a mail as important</label><input type="text" id="mail-cat" value="' + esc(S.mailCat) + '">' +
    '<label for="kw-input">Keywords in sender or title</label><form class="addrow" id="kw-form"><input type="text" id="kw-input" placeholder="Person or word"><button class="btn" type="submit">Add</button></form>' +
    '<div class="kws">' + S.kw.map(function (k, i) { return '<span class="kw">' + esc(k) + '<button type="button" data-kwdel="' + i + '" aria-label="Remove ' + esc(k) + '">×</button></span>'; }).join('') + '</div></details>';
  return h;
}

function briefHTML(g) {
  var failed = D.pipes.filter(function (p) { return p.c === "crit"; });
  var prBad = D.prs.filter(function (p) { return p.c === "crit"; });
  var prWait = D.prs.filter(function (p) { return p.c === "warn"; });
  var open = D.tasks.filter(function (t) { return !t.done; });
  var first = [];
  g.imp.slice(0, 3).forEach(function (x) { first.push('<span class="k">Mail</span>' + esc(x.m.from) + ': ' + esc(x.m.subj)); });
  failed.forEach(function (p) { first.push('<span class="k">Pipeline</span>' + esc(p.n) + ' failed on ' + esc(p.b)); });
  prBad.forEach(function (p) { first.push('<span class="k">PR</span>' + esc(p.t) + ' has a failing build'); });
  var day = D.cal.map(function (c) { return '<span class="k">' + c.t + '</span>' + esc(c.e); });
  var work = open.slice(0, 3).map(function (t) { return '<span class="k">Task</span>' + esc(t.d); });
  prWait.forEach(function (p) { work.push('<span class="k">PR</span>Waiting for review: ' + esc(p.t)); });
  var date = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  var lead = plural(g.imp.length, "important mail") + ", " + plural(failed.length, "failed pipeline") + " and " + plural(D.cal.length, "meeting") + ". First meeting at " + D.cal[0].t + ".";
  var ul = function (a, none) { return '<ul>' + (a.length ? a.map(function (x) { return '<li>' + x + '</li>'; }).join('') : '<li class="muted">' + none + '</li>') + '</ul>'; };
  return '<section class="panel brief c12"><div class="date">Daily brief · ' + date + '</div><div class="lead">' + lead + '</div><div class="bcols">' +
    '<div><h3>Needs you first</h3>' + ul(first, 'Nothing urgent.') + '</div>' +
    '<div><h3>Your day</h3>' + ul(day, 'No meetings.') + '</div>' +
    '<div><h3>Open work</h3>' + ul(work, 'Nothing open.') + '</div></div></section>';
}

function renderToday() {
  var g = groupMails();
  var h = '<div class="grid">' + briefHTML(g);
  h += panel("c4", "Calendar", "Microsoft Graph /me/calendarView", D.cal.map(function (c) {
    return linkRow(c, 0, '<span class="time">' + c.t + '</span><div class="main"><div class="t">' + c.e + '</div><div class="s">' + c.s + '</div></div>', ''); }).join(""));
  h += panel("c4", "Mail", "Graph /me/messages, categories", mailBody(g));
  h += panel("c4", "Vault tasks", "Obsidian, Tasks plugin syntax", D.tasks.map(function (t, i) {
    return '<label class="chk"><input type="checkbox" data-task="' + i + '"' + (t.done ? ' checked' : '') + '><span>' + t.d + '<br><span class="tag">' + t.f + '</span></span></label>'; }).join(""));
  h += panel("c6", "Pull requests", "Azure DevOps REST /git/pullrequests", D.prs.map(function (p) {
    return '<div class="row"><div class="main"><div class="t">' + p.t + '</div><div class="s">' + p.a + ', ' + p.age + ' old, ' + p.chk + '</div></div><span class="pill ' + p.c + '">' + p.st + '</span></div>'; }).join(""));
  h += panel("c6", "Pipelines", "Azure DevOps REST /build/builds", D.pipes.map(function (p) {
    return '<div class="row"><div class="main"><div class="t">' + p.n + '</div><div class="s mono">' + p.b + ', ' + p.d + ', ' + p.w + '</div></div><span class="pill ' + p.c + '">' + p.s + '</span></div>'; }).join(""));
  var cols = Object.keys(D.board).map(function (k) {
    return '<div class="col"><h3><span>' + k + '</span><span class="mono">' + D.board[k].length + '</span></h3>' + D.board[k].map(function (c) {
      return '<div class="card"><span class="id">' + c[0] + '</span>' + c[1] + '</div>'; }).join("") + '</div>'; }).join("");
  h += '<section class="panel c12"><div class="ph"><h2>Taskboard, Sprint 41</h2><span class="src">Azure DevOps REST /wit/wiql</span></div><div class="board">' + cols + '</div></section>';
  h += '</div><p class="note">All figures are mock data. The grey line on each panel names the API the live version would read from. Importance rules are saved in this browser.</p>';
  $("#view").innerHTML = h;
  document.querySelectorAll("[data-task]").forEach(function (el) {
    el.addEventListener("change", function () { D.tasks[+el.dataset.task].done = el.checked ? 1 : 0; renderToday(); });
  });
  var cfg = $("#cfg");
  cfg.addEventListener("toggle", function () { S.cfgOpen = cfg.open; });
  $("#mail-cat").addEventListener("change", function (e) { S.mailCat = e.target.value; savePrefs(); renderToday(); });
  $("#kw-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var v = $("#kw-input").value.trim();
    if (v && !S.kw.some(function (k) { return k.toLowerCase() === v.toLowerCase(); })) { S.kw.push(v); savePrefs(); }
    S.cfgOpen = true; renderToday(); $("#kw-input").focus();
  });
  document.querySelectorAll("[data-kwdel]").forEach(function (b) {
    b.addEventListener("click", function () { S.kw.splice(+b.dataset.kwdel, 1); savePrefs(); S.cfgOpen = true; renderToday(); });
  });
}
function panel(cls, title, src, body) {
  return '<section class="panel ' + cls + '"><div class="ph"><h2>' + title + '</h2><span class="src">' + src + '</span></div><div class="pb">' + body + '</div></section>';
}

/* ---------- AI ARCHITECTURE ---------- */
var CATS = [
  { id: "Analysis", c: "var(--c-analysis)" }, { id: "Design", c: "var(--c-design)" }, { id: "Development", c: "var(--c-dev)" },
  { id: "Review", c: "var(--c-review)" }, { id: "Communication", c: "var(--c-comm)" }, { id: "Operations", c: "var(--c-ops)" }
];
var starCss = null;
function stars() {
  if (starCss) return starCss;
  var seed = 7, out = [];
  function r() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
  for (var i = 0; i < 90; i++) out.push(Math.round(r() * 1600) + "px " + Math.round(r() * 1100) + "px 0 " + (r() > .85 ? "1px" : "0") + " rgba(255,255,255," + (0.25 + r() * 0.6).toFixed(2) + ")");
  starCss = out.join(",");
  return starCss;
}
function inSet() { var s = {}; WF[S.wf].nodes.forEach(function (n) { if (n.r) { s[n.r] = 1; if (n.k === "agent") AGENTS[n.r].skills.forEach(function (k) { s[k] = 1; }); } }); return s; }
function skillOwners(id) { return Object.keys(AGENTS).filter(function (a) { return AGENTS[a].skills.indexOf(id) > -1; }); }
function agentRow(a) {
  var o = AGENTS[a], n = o.skills.length;
  var moons = o.skills.map(function (s, i) {
    var ang = Math.round(-90 + (360 / n) * i + (n === 1 ? 45 : 0));
    return '<button type="button" class="moon" data-type="skill" data-ref="' + s + '" style="transform: rotate(' + ang + 'deg) translateX(48px)" aria-label="Skill ' + s + '"></button>';
  }).join("");
  var sks = n ? o.skills.map(function (s) { return '<button type="button" class="sk" data-type="skill" data-ref="' + s + '">' + s + '</button>'; }).join("") : '<span class="none">No skills</span>';
  return '<div class="ag"><div class="orb">' + (n ? '<div class="ring">' + moons + '</div>' : '') +
    '<button type="button" class="planet" data-type="agent" data-ref="' + a + '" aria-label="Agent ' + a + '"></button></div>' +
    '<div class="agt"><button type="button" class="an" data-type="agent" data-ref="' + a + '">' + a + '</button><div class="d">' + o.d + '</div><div class="sks">' + sks + '</div></div></div>';
}
function spaceHTML() {
  var cells = CATS.map(function (cat) {
    var ags = Object.keys(AGENTS).filter(function (a) { return AGENTS[a].cat === cat.id; });
    return '<div class="sys" style="--pc:' + cat.c + '"><h3><span>' + cat.id + '</span><span class="cnt">' + plural(ags.length, "agent") + '</span></h3>' + ags.map(agentRow).join("") + '</div>';
  }).join("");
  var loose = Object.keys(SKILLS).filter(function (s) { return !skillOwners(s).length; });
  var belt = loose.length ? '<div class="belt"><span class="bl">Skills without an agent</span>' + loose.map(function (s) { return '<button type="button" class="sk" data-type="skill" data-ref="' + s + '">' + s + '</button>'; }).join("") + '</div>' : '';
  return '<section class="space"><div class="stars" style="box-shadow:' + stars() + '"></div><div class="sh"><h2>Agent constellation</h2><span>Planet = agent, moon = skill, glow ring = used by the selected workflow</span></div>' +
    '<div class="systems">' + cells + '</div>' + belt + '<div class="scap" id="scap"></div></section>';
}
function mapState() {
  var ins = inSet();
  document.querySelectorAll(".space [data-ref]").forEach(function (el) {
    var on = S.ref && S.ref.type === el.dataset.type && S.ref.id === el.dataset.ref;
    el.setAttribute("aria-pressed", on ? "true" : "false");
    if (ins[el.dataset.ref]) el.setAttribute("data-in", "1"); else el.removeAttribute("data-in");
  });
  var cap = 'Select a planet or moon to see where it is used.';
  if (S.ref) {
    var n = usedIn(S.ref.type, S.ref.id).length;
    cap = 'Selected ' + S.ref.type + ' <b>' + S.ref.id + '</b>, used in ' + plural(n, "workflow") + (n ? ', marked below.' : '.');
  }
  $("#scap").innerHTML = cap;
}
function filtersHTML() {
  return '<button type="button" class="chip" data-theme-f="all" aria-pressed="' + (S.theme === "all") + '">All themes</button>' +
    THEMES.map(function (t) { return '<button type="button" class="chip" data-theme-f="' + t.id + '" aria-pressed="' + (S.theme === t.id) + '">' + t.name + '</button>'; }).join("");
}
function listHTML() {
  var hits = S.ref ? usedIn(S.ref.type, S.ref.id) : [];
  return THEMES.filter(function (t) { return S.theme === "all" || S.theme === t.id; }).map(function (t) {
    return '<div class="theme"><h2>' + t.name + '</h2>' + t.projects.map(function (p) {
      return '<div class="proj"><h3>' + p.name + '</h3>' + p.wfs.map(function (id) {
        var w = WF[id];
        return '<button type="button" class="wf" data-wf="' + id + '" aria-pressed="' + (S.wf === id) + '"><span class="nm">' + w.n + '<span class="meta">' + w.nodes.length + ' nodes, last run ' + w.run + '</span></span>' +
          (hits.indexOf(id) > -1 ? '<span class="pill acc">uses ' + S.ref.id + '</span>' : '') + '<span class="eng">' + w.eng + '</span><span class="pill ' + w.c + '" aria-hidden="true">●</span></button>';
      }).join("") + '</div>'; }).join("") + '</div>';
  }).join("");
}
function renderAI() {
  $("#view").innerHTML = spaceHTML() + '<h2 class="sec">Workflows</h2><div class="filters" id="filters">' + filtersHTML() + '</div><div class="split"><div id="wflist">' + listHTML() + '</div><section class="panel detail" id="detail">' + detailHTML() + '</section></div>' +
    '<p class="note">Mock data. The live version builds this from SKILL.md and agent files in your repos and from the n8n API (GET /workflows).</p>';
  mapState(); fitCanvas();
}
function applyAll(reset) {
  var sc = $("#cvs"), left = sc && !reset ? sc.scrollLeft : 0;
  $("#wflist").innerHTML = listHTML(); $("#detail").innerHTML = detailHTML(); mapState(); fitCanvas();
  if ($("#cvs")) $("#cvs").scrollLeft = left;
}
function refBtn(type, id) {
  var on = S.ref && S.ref.id === id && S.ref.type === type;
  return '<button type="button" class="ref" style="--kc:' + KC[type] + '" data-type="' + type + '" data-ref="' + id + '" aria-pressed="' + !!on + '">' + type + ': ' + id + '</button>';
}
/* ---------- n8n style flow ---------- */
var ICONS = {
  trigger: '<path d="M13 2L5 14h6l-1 8 8-12h-6z"/>',
  agent: '<rect x="5" y="8" width="14" height="11" rx="3"/><circle cx="9.5" cy="13.5" r="1"/><circle cx="14.5" cy="13.5" r="1"/><path d="M12 8V5"/><circle cx="12" cy="4" r="1"/>',
  skill: '<path d="M5 5h10a3 3 0 0 1 3 3v11H8a3 3 0 0 1-3-3z"/><path d="M8 5v11"/>',
  tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.4 2.4-2.3-.7-.7-2.3z"/>',
  mcp: '<path d="M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4"/>',
  model: '<path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/>',
  memory: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
  gate: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/>',
  if: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="9" r="2"/><path d="M6 7v10M18 11c0 4-4 4-8 5"/>'
};
var KLABEL = { trigger: "Trigger", agent: "Agent", skill: "Skill", tool: "Tool", mcp: "MCP tool", model: "Chat model", memory: "Memory", gate: "Human gate", if: "Branch" };
function icon(k, px) { return '<svg viewBox="0 0 24 24" width="' + px + '" height="' + px + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICONS[k] + '</svg>'; }
function wb(s) { return esc(s).replace(/-/g, "-<wbr>"); }
var NODE = 56, AW = 132, SUBD = 42, GAP = 62, MINCOL = 148, TOPY = 104, SUBY = 214, PAD = 40, lastGraph = null;
function agentSubs(aid) {
  var a = AGENTS[aid], s = [{ k: "model", port: "Model", w: a.model, y: "Chat model used by this agent." }];
  if (a.mem) s.push({ k: "memory", port: "Memory", w: a.mem, y: "Memory the agent reads and writes between runs." });
  a.mcp.forEach(function (m) { s.push({ k: "mcp", port: "MCP", w: m, y: "MCP server the agent can call as a tool." }); });
  a.skills.forEach(function (sk) { s.push({ k: "skill", port: "Skill", w: sk, r: sk, rt: "skill", y: SKILLS[sk].d }); });
  return s;
}
function buildGraph(id) {
  var w = WF[id], nodes = [], edges = [], pos = {}, order = w.nodes.map(function (n) { return n.id; }), x = PAD, hasSubs = false;
  w.nodes.forEach(function (n) {
    var subs = n.k === "agent" ? agentSubs(n.r) : [];
    var colw = Math.max(MINCOL, subs.length * GAP + 24), cx = x + colw / 2; x += colw;
    var o = { id: n.id, k: n.k, w: n.w, y: n.y, r: n.r, rt: n.k === "agent" ? "agent" : (n.k === "skill" ? "skill" : null), cx: cx, cy: TOPY, wd: n.k === "agent" ? AW : NODE, ht: NODE, sub: false };
    nodes.push(o); pos[n.id] = o;
    subs.forEach(function (s, j) {
      hasSubs = true;
      var sx = cx - (subs.length - 1) * GAP / 2 + j * GAP, m = subs.length;
      var px = m > 1 ? cx - (AW / 2 - 14) + j * ((AW - 28) / (m - 1)) : cx;
      nodes.push({ id: n.id + ":" + j, k: s.k, w: s.w, y: s.y, r: s.r, rt: s.rt || null, port: s.port, cx: sx, cy: SUBY, wd: SUBD, ht: SUBD, sub: true });
      edges.push({ t: "sub", x1: sx, y1: SUBY - SUBD / 2, x2: px, y2: TOPY + NODE / 2 });
    });
  });
  w.e.forEach(function (e) {
    var a = pos[e[0]], b = pos[e[1]], loop = order.indexOf(e[1]) <= order.indexOf(e[0]);
    edges.push({ t: loop ? "loop" : "main", x1: a.cx + a.wd / 2 + 2, x2: b.cx - b.wd / 2 - 2, y: TOPY, label: e[2] || "" });
  });
  var byId = {}; nodes.forEach(function (n) { byId[n.id] = n; });
  lastGraph = { nodes: nodes, edges: edges, byId: byId, w: x + PAD, h: hasSubs ? 300 : TOPY + NODE / 2 + 52 };
  return lastGraph;
}
function svgHTML(g) {
  var s = '<svg class="cvsvg" width="' + g.w + '" height="' + g.h + '" viewBox="0 0 ' + g.w + ' ' + g.h + '" aria-hidden="true"><defs>' +
    '<marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" style="fill:var(--cv-line)"/></marker>' +
    '<marker id="arl" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" style="fill:var(--cv-loop)"/></marker></defs>';
  g.edges.forEach(function (e) {
    if (e.t === "sub") {
      var my = (e.y1 + e.y2) / 2;
      s += '<path class="e sub" d="M' + e.x1 + ' ' + e.y1 + ' C' + e.x1 + ' ' + my + ' ' + e.x2 + ' ' + my + ' ' + e.x2 + ' ' + e.y2 + '"/>' +
        '<rect x="' + (e.x2 - 3.5) + '" y="' + (e.y2 - 3.5) + '" width="7" height="7" transform="rotate(45 ' + e.x2 + ' ' + e.y2 + ')" style="fill:var(--cv-line)"/>';
    } else if (e.t === "main") {
      s += '<path class="e" d="M' + e.x1 + ' ' + e.y + ' H' + e.x2 + '" marker-end="url(#ar)"/>';
      if (e.label) s += '<text class="elab" x="' + (e.x1 + 8) + '" y="' + (e.y - 7) + '">' + esc(e.label) + '</text>';
    } else {
      var top = 24;
      s += '<path class="e loop" d="M' + e.x1 + ' ' + e.y + ' H' + (e.x1 + 22) + ' V' + top + ' H' + (e.x2 - 22) + ' V' + e.y + ' H' + e.x2 + '" marker-end="url(#arl)"/>' +
        '<text class="elab loop" x="' + ((e.x1 + e.x2) / 2) + '" y="' + (top - 7) + '" text-anchor="middle">' + esc(e.label || "loop") + '</text>';
    }
  });
  return s + '</svg>';
}
function nodeHTML(n) {
  var sel = (S.node === n.id) || (S.ref && n.r && n.r === S.ref.id && n.rt === S.ref.type);
  var left = n.cx - n.wd / 2, top = n.cy - n.ht / 2;
  var st = 'left:' + left + 'px;top:' + top + 'px;width:' + n.wd + 'px;height:' + n.ht + 'px';
  var ic = '<span class="ic" style="color:var(--nk-' + n.k + ')">' + icon(n.k, n.k === "agent" ? 22 : (n.sub ? 18 : 26)) + '</span>';
  var inner = n.k === "agent" ? ic + '<span class="ag2">' + wb(n.r) + '</span>' : ic;
  var h = '<button type="button" class="nd ' + n.k + (n.sub ? ' sub' : '') + '" data-nid="' + esc(n.id) + '" aria-pressed="' + (sel ? "true" : "false") + '" aria-label="' + KLABEL[n.k] + ': ' + esc(n.w) + '" style="' + st + '">' + inner + '</button>';
  if (n.k === "agent") h += '<span class="nt" style="left:' + left + 'px;top:' + (top - 4) + 'px;width:' + n.wd + 'px">' + wb(n.w) + '</span>';
  else if (n.sub) h += '<span class="nl s" style="left:' + (n.cx - 31) + 'px;top:' + (top + n.ht + 6) + 'px;width:62px">' + wb(n.w) + '</span><span class="pl" style="left:' + n.cx + 'px;top:' + (top - 14) + 'px">' + n.port + '</span>';
  else h += '<span class="nl" style="left:' + (n.cx - 64) + 'px;top:' + (top + n.ht + 6) + 'px;width:128px">' + wb(n.w) + '</span>';
  return h;
}
function legendHTML() {
  var ks = ["trigger", "agent", "skill", "tool", "mcp", "model", "memory", "gate", "if"];
  return '<div class="cvleg">' + ks.map(function (k) { return '<span><i style="color:var(--nk-' + k + ');display:inline-grid">' + icon(k, 14) + '</i>' + KLABEL[k] + '</span>'; }).join("") +
    '<span>- - - resources of an agent</span><span style="color:var(--cv-loop)">&#8635; loop back</span></div>';
}
function detailHTML() {
  var w = WF[S.wf], pr = projOf(S.wf), g = buildGraph(S.wf);
  return '<div class="dh"><div class="dtop"><div><div class="crumbs">' + pr.t + ' / ' + pr.p + ' / ' + w.eng + '</div><h2>' + w.n + '</h2></div>' +
    '<div class="zoom" role="group" aria-label="Zoom"><button type="button" data-zoom="out" aria-label="Zoom out">&#8722;</button><button type="button" data-zoom="fit">Fit</button><button type="button" data-zoom="in" aria-label="Zoom in">+</button></div></div><p>' + w.desc + '</p></div>' +
    '<div class="cvs" id="cvs"><div class="cvbox" id="cvbox"><div class="cvi" id="cvi" data-w="' + g.w + '" data-h="' + g.h + '" style="width:' + g.w + 'px;height:' + g.h + 'px">' + svgHTML(g) + g.nodes.map(nodeHTML).join("") + '</div></div></div>' +
    legendHTML() + '<div style="padding-top:12px">' + nodeCard() + '</div>';
}
function nodeCard() {
  var n = S.node && lastGraph.byId[S.node], h = "";
  if (n) h += '<div class="insp"><h3>' + (n.r ? 'Step' : KLABEL[n.k]) + ': ' + esc(n.w) + '</h3><p style="margin:6px 0 0">' + esc(n.y) + '</p></div>';
  return h + ((S.ref || !n) ? inspector() : "");
}
function fitCanvas() {
  var sc = $("#cvs"); if (!sc) return;
  var inner = $("#cvi"), wd = +inner.dataset.w, ht = +inner.dataset.h, avail = sc.clientWidth || wd;
  var z = S.zoom == null ? Math.max(0.7, Math.min(1, avail / wd)) : S.zoom;
  S.zoomShown = z;
  inner.style.transform = "scale(" + z + ")";
  $("#cvbox").style.width = Math.round(wd * z) + "px"; $("#cvbox").style.height = Math.round(ht * z) + "px";
}
window.addEventListener("resize", function () { if (S.view === "ai" && S.zoom == null) fitCanvas(); });
function inspector() {
  if (!S.ref) return '<div class="insp"><span class="empty">Select an agent or skill, here or in the constellation, to see its definition and where else it is used.</span></div>';
  var type = S.ref.type, id = S.ref.id, o = (type === "agent" ? AGENTS : SKILLS)[id];
  var uses = usedIn(type, id).filter(function (k) { return k !== S.wf; });
  var h = '<div class="insp"><h3 style="color:' + KC[type] + '">' + type + ': ' + id + '</h3><div class="path">' + o.p + '</div><p style="margin:8px 0 0">' + o.d + '</p><dl>';
  if (type === "agent") h += '<dt>Category</dt><dd>' + o.cat + '</dd><dt>Uses skills</dt><dd>' + (o.skills.length ? o.skills.map(function (s) { return refBtn("skill", s); }).join("") : '<span class="empty">None</span>') + '</dd>';
  if (type === "skill") { var by = skillOwners(id);
    h += '<dt>Used by agents</dt><dd>' + (by.length ? by.map(function (a) { return refBtn("agent", a); }).join("") : '<span class="empty">None, called directly</span>') + '</dd>'; }
  h += '<dt>Also in</dt><dd>' + (uses.length ? uses.map(function (k) { return '<button type="button" class="chip" data-goto="' + k + '">' + WF[k].n + '</button>'; }).join("") : '<span class="empty">No other workflow</span>') + '</dd></dl></div>';
  return h;
}
$("#view").addEventListener("click", function (e) {
  if (S.view !== "ai") return;
  var t = e.target.closest("[data-nid]");
  if (t) { var n = lastGraph.byId[t.dataset.nid]; S.node = n.id; S.ref = n.r ? { type: n.rt, id: n.r } : null; applyAll(); return; }
  t = e.target.closest("[data-zoom]");
  if (t) { var z = S.zoomShown || 1, d = t.dataset.zoom; S.zoom = d === "fit" ? null : Math.max(0.5, Math.min(1.5, z + (d === "in" ? 0.1 : -0.1))); fitCanvas(); return; }
  t = e.target.closest("[data-ref]");
  if (t) { var same = S.ref && S.ref.id === t.dataset.ref && S.ref.type === t.dataset.type; S.ref = same ? null : { type: t.dataset.type, id: t.dataset.ref }; S.node = null; applyAll(); return; }
  t = e.target.closest("[data-wf],[data-goto]");
  if (t) { S.wf = t.dataset.wf || t.dataset.goto; S.node = null; if (t.dataset.wf) S.ref = null; applyAll(true); if (innerWidth <= 1000) $("#detail").scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  t = e.target.closest("[data-theme-f]");
  if (t) { S.theme = t.dataset.themeF; $("#filters").innerHTML = filtersHTML(); $("#wflist").innerHTML = listHTML(); }
});

/* ---------- VOICE COMMANDS ---------- */
var V = { sample: null, busy: false, rec: null, tools: false, failed: false };
function refresh() { S.view === "today" ? renderToday() : renderAI(); }
var ACTIONS = {
  show_view: { d: "Switch the dashboard to the Today view or the AI architecture view.", p: { view: { type: "string", enum: ["today", "ai"] } },
    f: function (a) { if (a.view !== "today" && a.view !== "ai") throw new Error("view must be today or ai"); show(a.view); return "Showing " + a.view; } },
  open_workflow: { d: "Open a workflow by id in the AI architecture view and show its flow.", p: { id: { type: "string" } },
    f: function (a) { if (!WF[a.id]) throw new Error("Unknown workflow id " + a.id); S.wf = a.id; S.ref = null; S.node = null; S.theme = "all"; show("ai"); return "Opened workflow " + WF[a.id].n; } },
  select_agent_or_skill: { d: "Highlight an agent or a skill by id in the AI architecture view and show where it is used.", p: { id: { type: "string" } },
    f: function (a) { var t = AGENTS[a.id] ? "agent" : (SKILLS[a.id] ? "skill" : null); if (!t) throw new Error("Unknown agent or skill " + a.id); S.ref = { type: t, id: a.id }; S.node = null; show("ai"); return "Selected " + t + " " + a.id; } },
  add_mail_keyword: { d: "Add a keyword (a person or a word) that marks mail as important when it appears in the sender or title.", p: { word: { type: "string" } },
    f: function (a) { var v = String(a.word || "").trim(); if (!v) throw new Error("Empty keyword"); if (!S.kw.some(function (k) { return k.toLowerCase() === v.toLowerCase(); })) { S.kw.push(v); savePrefs(); } S.cfgOpen = true; if (S.view !== "today") show("today"); else renderToday(); return "Added keyword " + v; } },
  remove_mail_keyword: { d: "Remove a mail importance keyword.", p: { word: { type: "string" } },
    f: function (a) { var v = String(a.word || "").toLowerCase(); var n = S.kw.length; S.kw = S.kw.filter(function (k) { return k.toLowerCase() !== v; }); if (S.kw.length === n) throw new Error("No such keyword"); savePrefs(); if (S.view === "today") renderToday(); return "Removed keyword " + a.word; } },
  add_task: { d: "Add a task to the vault task list.", p: { text: { type: "string" } },
    f: function (a) { var v = String(a.text || "").trim(); if (!v) throw new Error("Empty task"); D.tasks.unshift({ d: v, f: "Inbox.md", done: 0 }); if (S.view !== "today") show("today"); else renderToday(); return "Added task " + v; } },
  set_task_done: { d: "Mark a vault task done or open again, by its index in the task list.", p: { index: { type: "number" }, done: { type: "boolean" } },
    f: function (a) { var t = D.tasks[Number(a.index)]; if (!t) throw new Error("No task at that index"); t.done = a.done ? 1 : 0; if (S.view !== "today") show("today"); else renderToday(); return (t.done ? "Completed " : "Reopened ") + t.d; } }
};
function stateJSON() {
  return JSON.stringify({ view: S.view, openWorkflow: S.wf,
    workflows: Object.keys(WF).map(function (k) { return { id: k, name: WF[k].n, project: projOf(k).p }; }),
    agents: Object.keys(AGENTS).map(function (a) { return { id: a, category: AGENTS[a].cat }; }), skills: Object.keys(SKILLS),
    mailKeywords: S.kw, tasks: D.tasks.map(function (t, i) { return { index: i, text: t.d, done: !!t.done }; }) });
}
function buildTools(acted) {
  return Object.keys(ACTIONS).map(function (k) {
    return { name: k, description: ACTIONS[k].d, inputSchema: { type: "object", properties: ACTIONS[k].p, required: Object.keys(ACTIONS[k].p) },
      execute: function (a) { var r = ACTIONS[k].f(a || {}); acted.push(r); return r; } };
  });
}
var INTRO = "You operate a personal dashboard on behalf of the user. The user spoke or typed a command; speech recognition may have garbled it, and it may be Danish or English. " +
  "Carry it out with the tools. If it is only a question or nothing matches, do not call a tool. Finish with one short sentence in the user's language saying what you did or why you could not.\n\nDashboard state:\n" ;
function vlog(cls, text) {
  var d = document.createElement("div"); d.className = "vl " + cls; d.textContent = text;
  var l = $("#vlog"); l.appendChild(d); while (l.children.length > 8) l.removeChild(l.firstChild); l.scrollTop = l.scrollHeight;
}
function vstatus(t) { $("#vstatus").textContent = t; }
function errCopy(c) {
  return { not_granted: "Claude access was declined for this page.", sampling_disabled: "Claude is not available for this account.", rate_limited: "Too many requests. Try again in a minute.", session_expired: "Sign in again to continue." }[c] || "Could not reach Claude. Try again.";
}
async function sendCommand(text) {
  if (V.busy || !V.sample) return;
  V.busy = true; vlog("me", text); vstatus("Thinking..."); $("#vsend").disabled = true;
  var acted = [];
  try {
    if (V.tools) {
      var res = await V.sample(INTRO + stateJSON() + '\n\nCommand: "' + text + '"', { modelTier: "quick", tools: buildTools(acted) });
      vlog("ai", res.text);
    } else {
      var out = await V.sample.json(INTRO.replace("with the tools", "by listing actions") + stateJSON() + "\n\nAvailable actions: " + JSON.stringify(Object.keys(ACTIONS).map(function (k) { return { name: k, does: ACTIONS[k].d, args: Object.keys(ACTIONS[k].p) }; })) +
        '\n\nReply with only JSON: {"actions":[{"name":string,"args":object}],"reply":string}\n\nCommand: "' + text + '"', { modelTier: "quick" });
      (out.actions || []).forEach(function (a) { try { if (ACTIONS[a.name]) ACTIONS[a.name].f(a.args || {}); } catch (e) { } });
      vlog("ai", out.reply || "Done.");
    }
  } catch (e) { if (e && e.code !== "cancelled") vlog("err", errCopy(e && e.code)); }
  finally { V.busy = false; vstatus(""); $("#vsend").disabled = false; $("#vinput").value = ""; }
}
function stopListening() { if (V.rec) { try { V.rec.stop(); } catch (e) { } } }
function startListening() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $("#mic");
  var fallback = function (m) { V.rec = null; mic.classList.remove("on"); vstatus(m); $("#vinput").focus(); };
  if (!SR) { fallback("No speech recognition here. Use your keyboard's dictation key."); return; }
  try {
    var r = new SR(), heard = ""; V.failed = false;
    r.lang = $("#vlang").value; r.interimResults = true; r.continuous = false;
    r.onresult = function (e) { var t = ""; for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript; heard = t; $("#vinput").value = t; };
    r.onerror = function (e) { V.failed = true; fallback(e.error === "not-allowed" || e.error === "service-not-allowed" ? "Microphone is blocked in this view. Use your keyboard's dictation key." : "Speech error: " + e.error); };
    r.onend = function () { V.rec = null; mic.classList.remove("on"); if (!V.failed && heard.trim()) sendCommand(heard.trim()); else if (!V.failed) vstatus("Heard nothing."); };
    V.rec = r; r.start(); mic.classList.add("on"); vstatus("Listening...");
  } catch (e) { fallback("Speech recognition failed to start. Type or dictate instead."); }
}
$("#mic").addEventListener("click", function () {
  var sheet = $("#vsheet");
  if (V.rec) { stopListening(); return; }
  if (sheet.hidden) { sheet.hidden = false; $("#mic").setAttribute("aria-expanded", "true"); startListening(); }
  else { sheet.hidden = true; $("#mic").setAttribute("aria-expanded", "false"); }
});
$("#vform").addEventListener("submit", function (e) { e.preventDefault(); var v = $("#vinput").value.trim(); if (v) sendCommand(v); });
$("#vclose").addEventListener("click", function () { stopListening(); $("#vsheet").hidden = true; $("#mic").setAttribute("aria-expanded", "false"); });
(function () {
  var p = (window.claude && window.claude.use) ? window.claude.use("sample") : Promise.resolve(null);
  p.then(function (s) {
    if (!s) return;
    V.sample = s; $("#voice").hidden = false;
    if (s.limits) s.limits().then(function (l) { V.tools = !!(l && l.tools); }).catch(function () { });
  }).catch(function () { });
})();

/* ---------- NAV ---------- */
function show(v) {
  S.view = v;
  $("#nav-today").setAttribute("aria-pressed", v === "today");
  $("#nav-ai").setAttribute("aria-pressed", v === "ai");
  v === "today" ? renderToday() : renderAI();
  window.scrollTo(0, 0);
}
$("#nav-today").addEventListener("click", function () { show("today"); });
$("#nav-ai").addEventListener("click", function () { show("ai"); });
loadPrefs();

/* ---------- BOOT ----------
   Added by the step 2 split. In the single-file PoC the mock constants
   were already defined when this ran, so `show("today")` could be
   synchronous. Now the data arrives over fetch, so render has to wait -
   otherwise the page paints empty panels and looks broken.

   On failure it still renders, so a dead backend shows the shell and an
   error rather than a blank page. */
(async function boot() {
  try {
    await bootData();
  } catch (e) {
    console.error("data load failed", e);
    var b = document.querySelector("#bar") || document.body;
    var w = document.createElement("div");
    w.textContent = "Kunne ikke hente data. Prøv ?mock=1 for mock-data.";
    w.style.cssText = "padding:8px 12px;font:12px/1.4 ui-monospace,monospace";
    b.appendChild(w);
  }
  show("today");
})();
