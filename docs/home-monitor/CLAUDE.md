# Home Monitor

Personal work dashboard for Nichlas (solution architect, Trustworks). One page that centralizes mail, calendar, Obsidian tasks, Azure DevOps, and a visual map of his AI architecture (agents, skills, workflows).

State: approved proof of concept with mock data. Goal of this repo: turn it into a working app with live data, hosted on his home server.

## How to work with Nichlas

- Be honest and short. No rephrasing, no summaries of why something is good.
- Never use em dashes, in code comments, docs or replies.
- Challenge requests that look vague or derail the task.
- Ask before building if you are below 90 percent sure what is required.
- Evaluate that each response actually answers the task.

## What exists

`poc/home-monitor.html` is one self-contained file: HTML, CSS, vanilla JS, no build step, no dependencies. Open it in a browser or serve the folder with `python3 -m http.server`. Screenshots are in `screenshots/`.

Two views:

1. Today: daily brief (generated from the data), calendar, mail, vault tasks, pull requests, pipelines, taskboard.
2. AI architecture: "Agent constellation" (agents as planets, skills as moons, grouped by category), a workflow list grouped by theme and project, and an n8n style flow canvas per workflow.

Behaviors that must survive the rewrite:

- Mail importance: a mail is important if it carries a configurable Outlook category (default "Important") or if sender or subject contains a keyword. Important mails sort first with the reason shown. Rules are editable in the UI.
- Calendar and mail rows are links. Items with a Teams join link open that link ("Join in Teams"), everything else opens the Outlook item ("Open in Outlook").
- Flow canvas: main chain left to right, agent resources hang below as dashed sub nodes (chat model, memory, MCP tools, skills), branch nodes have labeled true/false edges, loops are drawn as an arc above the chain back to an earlier node. Clicking a node shows its step, clicking an agent or skill shows its definition and where else it is used. Selecting something in the constellation marks the workflows that use it, selecting a workflow marks its agents and skills in the constellation.
- Voice: a mic button takes speech or typed text and hands it to Claude, which acts on the dashboard through a small set of actions (see `docs/ARCHITECTURE.md`).

## What is mock in the PoC

Everything in the `D`, `AGENTS`, `SKILLS`, `THEMES`, `WF` constants. Links to Outlook and Teams are fake ids. Added tasks are in memory only. Voice used the Artifact `sample` capability, which does not exist outside claude.ai, so the button is hidden when the page runs standalone. Browser speech recognition was blocked in the claude.ai frame, so it was never verified there.

## Read next

- `docs/ARCHITECTURE.md`: target architecture, data contracts, adapter details, voice, security.
- `docs/ROADMAP.md`: ordered steps with open decisions.

## Constraints

- Contains work mail and calendar. It must never be reachable from the public internet without authentication. Home server is a headless Ubuntu box behind Cloudflare, with Tailscale for admin and Nginx as reverse proxy. Default to Tailscale only access.
- No secrets in the repo or in the frontend. Tokens live in server side environment variables or a secrets file outside the repo.
- Keep the frontend dependency light. The PoC has none. Do not introduce a framework without asking.
- Keep the data contracts in `docs/ARCHITECTURE.md` stable. The UI renders from them, adapters produce them.
- Internal tool, neutral dark ops look **throughout**. Dark only. Semi dark
  is acceptable; a light theme is not, and nothing may flash light - no
  white flash on load, no light modal or toast over a dark page, no
  `prefers-color-scheme` light branch. Paint every surface explicitly so
  the page never borrows the host's background. Do not restyle with the
  Trustworks brand unless asked.

## Definition of done for each step

Runs locally, has a mock mode that needs no credentials, and the UI works unchanged when switching between mock and live.
