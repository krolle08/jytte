# Azure DevOps API - hands-on walkthrough

This document walks you through every HTTP call the Jytte F4 widget
(`app/widgets/azuredevops/`) makes against the Azure DevOps REST API.
Follow it top-to-bottom in Postman (or curl, or any HTTP client) to
prove the API surface works for your account before, during, or after
debugging the widget.

There are 11 requests total. None of them write anything - this is a
read-only tour.

## Prerequisites

1. A **Personal Access Token (PAT)** for Azure DevOps.
   Mint one at:
   ```
   https://dev.azure.com/<your-org>/_usersSettings/tokens
   ```

2. The PAT needs these scopes:
   - **Code: Read** (pull requests, repositories)
   - **Build: Read** (pipelines and runs)
   - **Work Items: Read** (WIQL queries, work item details)

3. Your org slug (`Trustworks` in the example below), project name
   (`App`), and your work email (used only as a sanity check; the API
   resolves identity from the PAT itself).

## The one rule that makes every call work

Azure DevOps uses **HTTP Basic Auth with an empty username and the PAT
as the password**. There is no Bearer token, no OAuth dance for
personal use.

`curl`:

```bash
curl -u ":<PAT>" "https://dev.azure.com/<org>/_apis/projects?api-version=7.1"
```

Postman: set Authorization to `Basic Auth`, leave Username blank, put
the PAT in Password.

You set this once at the **collection level** in Postman and every
request inside the collection inherits it.

## Postman one-time setup

1. Create an **Environment** named `Trustworks-ADO` with these
   variables:

   | Variable        | Initial value                                              | Type   |
   |-----------------|------------------------------------------------------------|--------|
   | `AZDO_ORG`      | `Trustworks`                                               | text   |
   | `AZDO_PROJECT`  | `App`                                                      | text   |
   | `AZDO_PAT`      | paste your PAT here                                        | secret |
   | `AZDO_USER_ID`  | leave empty (we fill it in after request 2)                | text   |
   | `AZDO_TEAM`     | leave empty (auto-resolved from request 8)                 | text   |

   Mark `AZDO_PAT` as **secret** so Postman masks it in the UI and
   never logs it in shared exports.

2. Create a **Collection** named `Jytte F4 ADO`.
   - Under **Authorization**, choose `Basic Auth`.
   - Username: leave empty.
   - Password: `{{AZDO_PAT}}`.

3. In the collection's **Variables** tab, define:

   ```
   BASE       = https://dev.azure.com/{{AZDO_ORG}}/{{AZDO_PROJECT}}
   ORG_BASE   = https://dev.azure.com/{{AZDO_ORG}}
   VSSPS_BASE = https://vssps.dev.azure.com/{{AZDO_ORG}}
   ```

   Now every request you add to this collection inherits both the auth
   and the URL bases.

## The 11 requests, in order

Each section below is one Postman request. Add them in this order so
later requests can use values produced by earlier ones.

### 1. Smoke test - "does my PAT work at all?"

```
GET  {{ORG_BASE}}/_apis/projects?api-version=7.1
```

**Expected**: HTTP 200, JSON body with `count` and `value[]` of
projects you can access. The list should include your project name.

**Failure modes**:
- HTTP 401: PAT wrong or expired. Re-mint at the URL in Prerequisites.
- HTTP 200 with `value: []`: org name is wrong (org exists but PAT
  has no project access).
- HTTP 203 with HTML body: you hit a sign-in page - the PAT was not
  sent (check that the Authorization tab is configured).

### 2. Resolve your user id

```
GET  {{VSSPS_BASE}}/_apis/connectionData?api-version=7.1-preview.1
```

**Why**: every "my PRs" / "PRs awaiting me" query needs a stable user
id (a GUID), not your email. This endpoint returns it directly.

**Expected**:

```json
{
  "authenticatedUser": {
    "id": "a13dca37-7f40-6626-b3cf-bc562ed4a111",
    "providerDisplayName": "Nichlas Madsen",
    ...
  }
}
```

**Action**: copy `authenticatedUser.id` into the `AZDO_USER_ID`
environment variable. All subsequent calls reference `{{AZDO_USER_ID}}`.

**Do NOT use** `https://app.vssps.visualstudio.com/_apis/profile/profiles/me`
(returns 401 with a `dev.azure.com`-scoped PAT) or
`{{VSSPS_BASE}}/_apis/graph/users?subjectTypes=aad` filtered by
mailAddress (returns empty descriptor for AAD-only users in many
orgs). `connectionData` is the canonical "who am I" call.

### 3. PRs I authored (open)

```
GET  {{BASE}}/_apis/git/pullrequests
       ?searchCriteria.status=active
       &searchCriteria.creatorId={{AZDO_USER_ID}}
       &api-version=7.1
```

**Expected**: HTTP 200 with `value[]` of pull request objects. Look at
`pullRequestId`, `title`, `repository.name`, `sourceRefName`,
`targetRefName`, `creationDate`.

**Pitfall**: if `creatorId` is empty or omitted, the endpoint silently
returns ALL active PRs in the project rather than just yours. Always
pass a non-empty user id.

### 4. PRs awaiting my review

```
GET  {{BASE}}/_apis/git/pullrequests
       ?searchCriteria.status=active
       &searchCriteria.reviewerId={{AZDO_USER_ID}}
       &api-version=7.1
```

**Expected**: HTTP 200 with PRs where you are listed as a reviewer.

To get *only* the PRs you still owe a review on, filter the response
client-side to entries where the `reviewers[]` entry matching your id
has `vote == 0` (or no vote entry at all).

**Vote semantics** (per ADO docs):

| Vote  | Meaning                       |
|-------|-------------------------------|
|  10   | Approved                      |
|   5   | Approved with suggestions     |
|   0   | No vote yet                   |
|  -5   | Waiting for author            |
| -10   | Rejected                      |

### 5. Recent pipeline runs

```
GET  {{BASE}}/_apis/build/builds
       ?$top=20
       &queryOrder=finishTimeDescending
       &api-version=7.1
```

**Expected**: 20 most recent builds, newest first.

Each build has:
- `status`: `notStarted | inProgress | completed | cancelling`
- `result`: only set when `status == completed`, one of
  `succeeded | failed | canceled | partiallySucceeded`
- `definition.name`: the pipeline name
- `sourceBranch`: e.g. `refs/heads/dev`

**Pitfall**: `statusFilter=inProgress,completed` returns HTTP 400 - the
parser dislikes the unencoded comma. Easier to request unfiltered and
filter client-side.

### 6. Latest run on a specific branch (the red-fail signal)

```
GET  {{BASE}}/_apis/build/builds
       ?branchName=refs/heads/dev
       &statusFilter=completed
       &$top=1
       &queryOrder=finishTimeDescending
       &api-version=7.1
```

Repeat this for each branch you care about (e.g. `refs/heads/main`
for repos that use it).

The Jytte widget calls this once per repo's actual default branch and
lights a red banner when any of those `result` values is not
`succeeded`.

### 7. List repos (to discover each repo's default branch)

```
GET  {{BASE}}/_apis/git/repositories?api-version=7.1
```

**Expected**: every repo in the project, each with a `name` and a
`defaultBranch` (e.g. `refs/heads/dev`).

**Why this matters**: default branches are **per-repo**, not
project-wide. In Trustworks/App, `app` and `backend` default to `dev`;
`infrastructure` defaults to `main`. Hard-coding `refs/heads/main` for
the whole project is wrong.

### 8. List teams in the project

```
GET  {{ORG_BASE}}/_apis/projects/{{AZDO_PROJECT}}/teams?api-version=7.1
```

**Expected**: `value[]` of teams, each with `id` and `name`.

The naming convention is usually `<Project Name> Team` (here:
`App Team`) but customers often rename it. If you set `AZDO_TEAM` to
the wrong value, request 9 returns 404.

**Action**: if `AZDO_TEAM` is empty, pick `value[0].name` and store it
in `AZDO_TEAM` for the next request.

### 9. Current iteration for that team

```
GET  {{BASE}}/{{AZDO_TEAM}}/_apis/work/teamsettings/iterations
       ?$timeframe=current
       &api-version=7.1
```

In Postman, **URL-encode the space** in the team name segment - Postman
does this for you when you use `{{AZDO_TEAM}}` in a path segment, but
if you type it manually use `App%20Team`.

**Expected**: HTTP 200 with `value[0]` describing the current
iteration. Read `value[0].path` (e.g. `App\Sprint 3`) - you need it for
the next request.

**Note**: `$timeframe=current` returns whatever iteration the team has
flagged as current right now, even if its calendar window is past. The
team may simply not have rolled to the next sprint yet.

### 10. WIQL query - my work items in that iteration

```
POST  {{BASE}}/_apis/wit/wiql?api-version=7.1
```

**Headers**:
```
Content-Type: application/json
```

**Body** (raw / JSON):
```json
{
  "query": "SELECT [System.Id] FROM workitems WHERE [System.AssignedTo] = @Me AND [System.IterationPath] = 'App\\Sprint 3' AND [System.State] <> 'Removed' ORDER BY [System.ChangedDate] DESC"
}
```

Substitute the actual iteration path from request 9. Note the
**double backslash** inside the JSON string.

**Expected**: a list of just IDs:

```json
{
  "workItems": [
    { "id": 1234, "url": "..." },
    { "id": 1235, "url": "..." }
  ]
}
```

The `@Me` macro resolves automatically to the PAT's owner - no need to
plug `AZDO_USER_ID` in here.

### 11. Fetch the actual fields for those IDs

```
GET  {{BASE}}/_apis/wit/workitems
       ?ids=1234,1235
       &fields=System.Id,System.Title,System.WorkItemType,System.State,System.Tags,System.AreaPath
       &api-version=7.1
```

Replace `1234,1235` with the IDs from request 10.

**Expected**: HTTP 200, `value[]` of full work-item objects. Each has a
`fields` map keyed by the field names you asked for.

**Limit**: cap at 200 IDs per call. If WIQL returns more, chunk them.

## Pitfalls cheat sheet

| Symptom                                                          | Cause                                                | Fix                                                            |
|------------------------------------------------------------------|------------------------------------------------------|----------------------------------------------------------------|
| HTTP 401 from `app.vssps.visualstudio.com/_apis/profile/profiles/me` | Wrong audience for a `dev.azure.com`-scoped PAT      | Use `{{VSSPS_BASE}}/_apis/connectionData` instead              |
| `graph/users` filter by `mailAddress` returns empty `descriptor` | AAD-only users not materialized in the org graph     | Same fix - use `connectionData`                                |
| HTTP 400 on `statusFilter=inProgress,completed`                  | Parser dislikes the unencoded comma                  | Drop the filter, sort + slice client-side                      |
| HTTP 404 on iteration request                                    | Wrong team name in the URL path                      | Run request 8, use `value[0].name` (or correct `AZDO_TEAM`)    |
| Latest-on-default returns 0 results                              | Default branch is `dev`, not `main`                  | Resolve `defaultBranch` per repo via request 7 first           |
| HTTP 200 with HTML response body (sign-in page)                  | PAT not sent, request hit web auth instead of API    | Re-check the Authorization tab is set to Basic Auth            |
| HTTP 203 (`Non-Authoritative Information`)                       | Same as HTML response - PAT missing                  | Same fix                                                       |

## How this maps to the F4 widget

The widget runs requests 3, 4, 5, 7, 8, 9, 10, 11 in parallel via
`asyncio.gather` on every refresh (default cadence: 5 minutes). Request
2 is cached for the lifetime of the widget process. Each section
(PRs / Pipelines / Tasks) is wrapped in its own error handler so a
failure in one does not sink the other two.

Source files:
- `app/widgets/azuredevops/ado.py` - the async client (one method per
  request above)
- `app/widgets/azuredevops/fetch.py` - the parallel refresh
- `app/widgets/azuredevops/card.html` - rendering
- `app/widgets/azuredevops/mcp.py` - the same data exposed as MCP tools

The skill at `~/.claude/skills/azure-devops/SKILL.md` is the
machine-readable version of this document - keep them in sync if you
add new operations.

## Security note

Never paste a PAT into a shared document, a Postman export, a screenshot,
or a Slack message. Treat it like a password.

- Mark `AZDO_PAT` as **secret** in the Postman environment so exports
  don't include it.
- Use `_apis/tokens/pat` (or the ADO UI) to revoke a PAT immediately if
  you suspect exposure.
- PAT expiry is configurable up to 1 year. For long-lived dev work,
  rotate quarterly.
