# Architecture

## Target shape

```
Browser (static frontend)  <--JSON-->  Backend (one process)  <--> adapters
                                                                   |- Microsoft Graph (mail, calendar)
                                                                   |- Obsidian vault (tasks)
                                                                   |- Azure DevOps REST (PRs, pipelines, board)
                                                                   |- Repo scanner (agents, skills)
                                                                   |- n8n API (workflows)
                                                                   '- Claude (voice commands)
```

The backend serves the static frontend and `GET /api/*` endpoints. Each adapter returns exactly one data contract below. No database. User settings (mail importance rules) are a JSON file on disk.

Every adapter has a mock implementation that returns the PoC data. The frontend never knows which one is active.

Backend language is an open decision, see `ROADMAP.md`.

## Data contracts

These are the shapes the PoC UI already renders. Field names match the PoC constants.

### GET /api/calendar

```ts
type CalEvent = {
  t: string;        // start time "09:00"
  e: string;        // title
  s: string;        // subtitle, e.g. location or "Teams, 45 min"
  web: string;      // Outlook web link (Graph event.webLink)
  teams?: string;   // join link (Graph event.onlineMeeting.joinUrl), present only for Teams meetings
};
```

### GET /api/mail

```ts
type Mail = {
  t: string;        // "08:12" today, weekday name or date otherwise
  from: string;     // display name
  subj: string;
  tag: string;      // short project tag, derived server side, may be empty
  unread: 0 | 1;
  cats: string[];   // Outlook categories (Graph message.categories)
  web: string;      // Graph message.webLink
  teams?: string;   // Teams join link found in the body, for meeting invites
};
```

Importance (`Outlook tag` or `Keyword: x`) is computed in the frontend from `cats` plus the rules in `GET/PUT /api/settings`. If rules should apply to push notifications later, move it to the backend.

### GET/PUT /api/settings

```ts
type Settings = { mailCategory: string; mailKeywords: string[] };
```

Replaces `localStorage` key `hm.mail`.

### GET /api/tasks

```ts
type Task = { d: string; f: string; done: 0 | 1 };  // text, vault file path, state
```

Source is open `- [ ]` and recently completed lines from the vault. `PATCH /api/tasks` should write the checkbox back to the markdown file. Tasks added by voice go to an inbox note.

### GET /api/devops

```ts
type DevOps = {
  prs: { t: string; a: string; st: string; c: "good" | "warn" | "crit"; age: string; chk: string }[];
  pipes: { n: string; b: string; s: string; c: "good" | "warn" | "crit"; d: string; w: string }[];
  board: Record<"New" | "Active" | "Review" | "Done", [id: string, title: string][]>;
};
```

`c` is the semantic color. Map: Passed or Approved = good, Running or Needs review = warn, Failed or Build failing = crit.

### GET /api/ai

The AI architecture view renders from this single document.

```ts
type AiModel = {
  agents: Record<string, {
    cat: string;          // category id, see `categories` below. Open set.
    d: string;            // description
    p: string;            // source path
    model: string;        // chat model label
    mcp: string[];        // MCP server names the agent can call
    mem: string | null;   // memory label
    skills: string[];     // skill ids
  } & Scope>;
  skills: Record<string, { d: string; p: string } & Scope>;

  // Categories are data, not a fixed enum. The scanner reads them from
  // themes.yaml so a new one does not need a code change.
  categories: { id: string; name: string; order: number }[];
  themes: { id: string; name: string; projects: { id: string; name: string; wfs: string[] }[] }[];
  workflows: Record<string, {
    n: string;            // name
    eng: string;          // engine label: "n8n", "Claude", "Azure + n8n"
    run: string;          // last run, e.g. "Passed, 08:00"
    c: "good" | "warn" | "crit";
    desc: string;
    nodes: {
      id: string;
      k: "trigger" | "agent" | "skill" | "tool" | "gate" | "if";
      w: string;          // step title
      y: string;          // step description
      r?: string;         // agent or skill id, required when k is agent or skill
    }[];
    e: [from: string, to: string, label?: string][];   // main edges; an edge to an earlier node is a loop
  }>;
};
```

```ts
// Where a capability lives, and whether the copies agree.
//
// Measured 2026-10-03: 418 agent and skill files across 30 .claude
// folders resolve to 42 distinct names, and 10 of those names exist in
// more than one version. Without this block the UI renders a drifted
// duplicate as if it were one clean capability, which is the single
// most misleading thing it could do.
type Scope = {
  scope: "global" | "project" | "both";
  origin: string;        // "~/.claude" or the project root that owns it
  usedBy: string[];      // project roots that reference it
  copies: number;        // .claude folders carrying this name, worktrees excluded
  versions: number;      // distinct content hashes; > 1 means drift
  runs?: number;         // observed invocations, from logs/agent-usage.jsonl
};
```

The UI uses `Scope` for three things: size a planet by `runs` rather than
uniformly, ring it when `versions > 1`, and let the view filter to
global, shared or drifted. A capability with `scope: "both"` is already
duplicated between `~/.claude` and a project and should be surfaced, not
merged silently.

Layout is automatic in the PoC: nodes in one row in array order, agent resources generated from the agent entry. If a workflow comes from n8n, use the node `position` values instead and add optional `x`, `y` to nodes. Needs a small change in `buildGraph`.

### POST /api/command

```ts
// request
{ text: string; state: object }   // state = same compact JSON the PoC sends (view, workflows, agents, skills, keywords, tasks)
// response
{ reply: string; actions: { name: string; args: object }[] }
```

Actions the frontend executes (names and arguments are in the `ACTIONS` object in the PoC): `show_view`, `open_workflow`, `select_agent_or_skill`, `add_mail_keyword`, `remove_mail_keyword`, `add_task`, `set_task_done`.

The backend calls Claude with the same tool definitions and returns the tool calls instead of executing them. The frontend executes them. The model never gets write access to anything except through these actions.

## Adapters

### Microsoft Graph (mail, calendar)

- Mail: `GET /me/mailFolders/inbox/messages?$select=id,receivedDateTime,from,subject,categories,isRead,webLink,bodyPreview,body&$top=50`. Teams invite detection: body contains `teams.microsoft.com/l/meetup-join`.
- Calendar: `GET /me/calendarView?startDateTime=..&endDateTime=..&$select=subject,start,end,location,webLink,isOnlineMeeting,onlineMeeting`. Use `onlineMeeting.joinUrl`.
- Auth needs an Entra app registration with delegated `Mail.Read` and `Calendars.Read`. In the Trustworks tenant this probably needs admin consent. Treat as the main risk and ask Nichlas early whether he can get it. Fallbacks to discuss: read through the Outlook MCP connector, or an n8n workflow that already holds the credentials and exposes a webhook.
- Do not use `mailto:` or custom URI schemes for deep links. Use `webLink` and `joinUrl`, which are https universal links.

### Obsidian vault

Vault is on Nichlas's computer, the server needs a copy. Open decision: Syncthing, git, or Obsidian Sync headless. Parse markdown for Tasks plugin syntax (`- [ ]`, due date after the calendar emoji). Watch the folder and cache.

### Azure DevOps

REST with a PAT stored server side. Active PRs: `_apis/git/pullrequests?searchCriteria.status=active`. Builds: `_apis/build/builds?$top=20`. Board: WIQL query for the current iteration, group by `System.State`. Org and project come from config.

### AI architecture scanner

- Agents: `.claude/agents/*.md` frontmatter (`name`, `description`, `model`, `tools`). Add `category` and optional `mcp`, `memory` keys to the frontmatter convention.
- Skills: `skills/*/SKILL.md` frontmatter (`name`, `description`).
- Which agent uses which skill: from the agent frontmatter or body references. Decide the convention with Nichlas.
- Themes and projects: a small `themes.yaml` he maintains. Nothing in the repos says this.
- n8n workflows: `GET /api/v1/workflows` with an API key. Map node types: `@n8n/n8n-nodes-langchain.agent` to `agent` (resources from `ai_languageModel`, `ai_memory`, `ai_tool` connections), `n8n-nodes-base.if` and `switch` to `if`, `splitInBatches` loops to loop edges, trigger nodes to `trigger`, everything else to `tool`. Last run from `GET /api/v1/executions`.
- Claude workflows (non n8n): need a description format. Propose YAML next to the agent files, same `nodes` and `e` shape as the contract.

## Voice

Frontend: Web Speech API (`SpeechRecognition`, `da-DK` or `en-US`). Needs a secure context, so serve over HTTPS (Tailscale serve gives this). Always keep the text field as fallback, mobile keyboard dictation works too. Backend: `POST /api/command` as above, rate limited, only reachable from the same origin.

## Security

- Tailscale only by default. If exposed through Cloudflare, put Cloudflare Access in front.
- Backend holds all tokens. Frontend gets data only.
- `/api/command` is a write path into the UI only. No action touches mail, calendar, DevOps or the vault, except `add_task` and `set_task_done` which write the vault.
- Treat mail subjects and bodies as untrusted text in any prompt (prompt injection). Do not pass mail content to the command endpoint.
