"""Async Azure DevOps REST client used by the F4 widget.

Every operation here is documented in the `azure-devops` skill at
~/.claude/skills/azure-devops/SKILL.md. Behaviour confirmed against the
Trustworks/App org during F4 spec accept:
  - User self-id via vssps connectionData (graph/users is empty for AAD-only users).
  - Default branch is per-repo, not project-wide.
  - Team name is not always "<Project> Team" - list teams and pick.

The client never logs the PAT. The `_auth` tuple is held only in memory.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

# Reviewer vote semantics from ADO:
VOTE_REJECTED = -10
VOTE_WAITING = -5
VOTE_NONE = 0
VOTE_APPROVED_SUGGESTIONS = 5
VOTE_APPROVED = 10

API_VERSION = "7.1"
API_VERSION_PREVIEW = "7.1-preview.1"


class ADOMisconfigured(RuntimeError):
    """Raised when required env vars are missing or empty."""


@dataclass
class ADOConfig:
    slug: str            # stable id used in URLs (e.g. "primary", "dagrofa")
    org: str
    project: str
    pat: str
    user_email: str
    team: Optional[str] = None  # auto-discovered if None
    enabled: bool = True  # False = configured but "dark": never contacted

    @property
    def base(self) -> str:
        return f"https://dev.azure.com/{self.org}/{self.project}"

    @property
    def org_base(self) -> str:
        return f"https://dev.azure.com/{self.org}"

    @property
    def vssps_base(self) -> str:
        return f"https://vssps.dev.azure.com/{self.org}"

    @property
    def label(self) -> str:
        """Human display label, e.g. 'Trustworks / App'."""
        return f"{self.org} / {self.project}"


_FALSEY = {"0", "false", "no", "off", "disabled"}


def _env_enabled(sep: str) -> bool:
    """Read AZDO_ENABLED[_SUFFIX]. Absent = enabled. A falsey value marks
    the instance 'configured but dark' - fetch/writer must never contact it.
    This is how an instance (e.g. Dagrofa) can be fully set up and still
    not touched until the operator flips the flag."""
    raw = os.getenv("AZDO_ENABLED" + sep)
    if raw is None:
        return True
    return raw.strip().lower() not in _FALSEY


def _build_config(suffix: str) -> ADOConfig:
    """Build a config for one suffix. Empty suffix means the default
    (unsuffixed) instance. Suffixes are kept upper-case in env vars but
    lower-cased for the slug so URL paths stay clean."""
    sep = "" if not suffix else "_" + suffix
    org = os.getenv("AZDO_ORG" + sep)
    project = os.getenv("AZDO_PROJECT" + sep)
    pat = os.getenv("AZDO_PAT" + sep)
    email = os.getenv("AZDO_USER_EMAIL" + sep)
    team = os.getenv("AZDO_TEAM" + sep)
    missing = [k for k, v in {"ORG": org, "PROJECT": project, "PAT": pat, "USER_EMAIL": email}.items() if not v]
    if missing:
        raise ADOMisconfigured(
            f"missing AZDO_{{{','.join(missing)}}}{sep} - instance '{suffix or 'primary'}' skipped"
        )
    slug = suffix.lower() if suffix else "primary"
    return ADOConfig(
        slug=slug, org=org, project=project, pat=pat,
        user_email=email, team=team or None,
        enabled=_env_enabled(sep),
    )


def discover_configs() -> list[ADOConfig]:
    """Find every ADO instance the operator has configured. The default
    (unsuffixed) AZDO_* group is always tried first; any AZDO_ORG_<SUFFIX>
    flags an additional instance with that suffix.

    Instances missing required vars are logged and skipped rather than
    raising, so partial configurations still surface the ones that work.
    """
    suffixes: set[str] = set()
    for key in os.environ:
        if not key.startswith("AZDO_ORG"):
            continue
        if key == "AZDO_ORG":
            suffixes.add("")
        elif key.startswith("AZDO_ORG_"):
            suffixes.add(key[len("AZDO_ORG_"):])

    # Empty suffix first, then alphabetical
    ordered = sorted(suffixes, key=lambda s: (1 if s else 0, s))

    configs: list[ADOConfig] = []
    for suffix in ordered:
        try:
            configs.append(_build_config(suffix))
        except ADOMisconfigured as e:
            log.warning("[ado] %s", e)
    return configs


# Kept for backward compat with any direct caller from earlier in the
# F4 build. Returns the FIRST discovered config or raises if none.
def _legacy_from_env() -> ADOConfig:
    configs = discover_configs()
    if not configs:
        raise ADOMisconfigured("no AZDO_* env vars configured")
    return configs[0]

ADOConfig.from_env = staticmethod(_legacy_from_env)  # type: ignore[assignment]


@dataclass
class ADOClient:
    config: ADOConfig
    timeout: float = 15.0
    _client: Optional[httpx.AsyncClient] = field(default=None, init=False, repr=False)
    _user_id: Optional[str] = field(default=None, init=False, repr=False)

    async def __aenter__(self) -> "ADOClient":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            auth=("", self.config.pat),  # empty username + PAT as password
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *exc):
        if self._client is not None:
            await self._client.aclose()
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ADOClient used outside async context manager")
        return self._client

    async def _get(self, url: str, **params: Any) -> dict:
        params.setdefault("api-version", API_VERSION)
        r = await self.client.get(url, params=params)
        if r.status_code in (401, 403):
            # do NOT echo the PAT or response body that might contain it
            raise httpx.HTTPStatusError(
                f"ADO auth failed ({r.status_code}); PAT may be expired or missing scopes",
                request=r.request, response=r,
            )
        r.raise_for_status()
        return r.json()

    async def _post(self, url: str, body: dict, **params: Any) -> dict:
        params.setdefault("api-version", API_VERSION)
        r = await self.client.post(url, params=params, json=body)
        r.raise_for_status()
        return r.json()

    # ------- identity -------

    async def resolve_user_id(self) -> str:
        if self._user_id:
            return self._user_id
        data = await self._get(
            f"{self.config.vssps_base}/_apis/connectionData",
            **{"api-version": API_VERSION_PREVIEW},
        )
        uid = (data.get("authenticatedUser") or {}).get("id")
        if not uid:
            raise RuntimeError("connectionData returned no authenticatedUser.id")
        self._user_id = uid
        return uid

    # ------- PRs -------

    async def list_my_authored_prs(self) -> list[dict]:
        me = await self.resolve_user_id()
        data = await self._get(
            f"{self.config.base}/_apis/git/pullrequests",
            **{
                "searchCriteria.status": "active",
                "searchCriteria.creatorId": me,
                "$top": 50,
            },
        )
        return [_normalize_pr(pr, me) for pr in data.get("value", [])]

    async def list_prs_awaiting_me(self) -> list[dict]:
        me = await self.resolve_user_id()
        data = await self._get(
            f"{self.config.base}/_apis/git/pullrequests",
            **{
                "searchCriteria.status": "active",
                "searchCriteria.reviewerId": me,
                "$top": 50,
            },
        )
        prs = [_normalize_pr(pr, me) for pr in data.get("value", [])]
        # Filter to those where I have NOT yet voted (vote 0 or missing).
        return [p for p in prs if p["my_vote"] in (None, VOTE_NONE)]

    # ------- pipelines -------

    async def list_repos(self) -> list[dict]:
        data = await self._get(f"{self.config.base}/_apis/git/repositories")
        return [
            {"id": r["id"], "name": r["name"], "default_branch": r.get("defaultBranch")}
            for r in data.get("value", [])
        ]

    async def recent_builds(self, top: int = 30) -> list[dict]:
        # Avoid the statusFilter=inProgress,completed combo which returns 400;
        # request unfiltered, sort newest-first, and trim client-side.
        data = await self._get(
            f"{self.config.base}/_apis/build/builds",
            **{"$top": top, "queryOrder": "finishTimeDescending"},
        )
        return [_normalize_build(b) for b in data.get("value", [])]

    async def latest_on_branch(self, branch: str, top: int = 1) -> list[dict]:
        data = await self._get(
            f"{self.config.base}/_apis/build/builds",
            **{
                "branchName": branch,
                "statusFilter": "completed",
                "$top": top,
                "queryOrder": "finishTimeDescending",
            },
        )
        return [_normalize_build(b) for b in data.get("value", [])]

    # ------- work items -------

    async def list_teams(self) -> list[dict]:
        data = await self._get(
            f"{self.config.org_base}/_apis/projects/{self.config.project}/teams",
        )
        return [{"id": t["id"], "name": t["name"]} for t in data.get("value", [])]

    async def resolve_team(self) -> str:
        if self.config.team:
            return self.config.team
        teams = await self.list_teams()
        if not teams:
            raise RuntimeError("no teams in project")
        return teams[0]["name"]

    async def current_iteration(self) -> Optional[dict]:
        team = await self.resolve_team()
        team_url = team.replace(" ", "%20")
        try:
            data = await self._get(
                f"{self.config.base}/{team_url}/_apis/work/teamsettings/iterations",
                **{"$timeframe": "current"},
            )
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise
        values = data.get("value") or []
        if not values:
            return None
        it = values[0]
        return {
            "name": it.get("name"),
            "path": it.get("path"),
            "start": (it.get("attributes") or {}).get("startDate"),
            "finish": (it.get("attributes") or {}).get("finishDate"),
        }

    async def workitem_comments(self, item_id: int, top: int = 20) -> list[dict]:
        """Fetch the newest comments on a work item. Called lazily by the
        drawer route (NOT the list fetch) so the 5-minute poll stays cheap.
        A 404 means the item has no comments thread yet -> empty list, not
        an error. The response body is never surfaced raw on auth failure."""
        url = f"{self.config.base}/_apis/wit/workItems/{int(item_id)}/comments"
        try:
            data = await self._get(
                url, **{"api-version": "7.1-preview.3", "$top": top, "order": "desc"},
            )
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 404:
                return []
            raise
        return [_normalize_comment(c) for c in (data.get("comments") or [])]

    async def my_workitems_in_iteration(self, iteration_path: str) -> list[dict]:
        # Escape single quotes in the iteration path per WIQL rules
        path_escaped = iteration_path.replace("'", "''")
        wiql = (
            "SELECT [System.Id] FROM workitems "
            "WHERE [System.AssignedTo] = @Me "
            f"AND [System.IterationPath] = '{path_escaped}' "
            "AND [System.State] <> 'Removed' "
            "ORDER BY [System.ChangedDate] DESC"
        )
        result = await self._post(
            f"{self.config.base}/_apis/wit/wiql",
            {"query": wiql},
        )
        ids = [str(w["id"]) for w in result.get("workItems") or []]
        if not ids:
            return []
        # Batch fetch fields (cap at 200 per call which is plenty for a sprint)
        details = await self._get(
            f"{self.config.base}/_apis/wit/workitems",
            **{
                "ids": ",".join(ids[:200]),
                "fields": (
                    "System.Id,System.Title,System.WorkItemType,System.State,"
                    "System.Tags,System.AreaPath,System.IterationPath,"
                    "System.Description,System.AssignedTo,"
                    "System.CreatedBy,System.CreatedDate,System.ChangedDate,"
                    "Microsoft.VSTS.Common.AcceptanceCriteria,"
                    "Microsoft.VSTS.Common.Priority,Microsoft.VSTS.Common.Severity,"
                    "Microsoft.VSTS.Scheduling.DueDate,Microsoft.VSTS.Scheduling.TargetDate"
                ),
            },
        )
        return [_normalize_workitem(w, self.config) for w in details.get("value", [])]


# ------- normalizers -------

def _normalize_pr(pr: dict, me: str) -> dict:
    reviewers = pr.get("reviewers") or []
    my_vote = next(
        (r.get("vote") for r in reviewers if r.get("id") == me),
        None,
    )
    repo = pr.get("repository") or {}
    return {
        "id": pr.get("pullRequestId"),
        "title": pr.get("title"),
        "description": pr.get("description"),  # PR body (markdown/plain in ADO)
        "repo": repo.get("name"),
        "source": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
        "target": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
        "created": pr.get("creationDate"),
        "my_vote": my_vote,
        "creator": (pr.get("createdBy") or {}).get("displayName"),
        "reviewers": [
            {
                "name": r.get("displayName"),
                "vote": r.get("vote", 0),
                "required": r.get("isRequired", False),
            }
            for r in reviewers
        ],
        "web_url": _pr_web_url(pr),
    }


def _pr_web_url(pr: dict) -> Optional[str]:
    links = pr.get("_links") or {}
    web = links.get("web") or {}
    if href := web.get("href"):
        return href
    repo = pr.get("repository") or {}
    project = (repo.get("project") or {}).get("name")
    repo_name = repo.get("name")
    pr_id = pr.get("pullRequestId")
    if project and repo_name and pr_id is not None:
        return f"https://dev.azure.com/_git/{repo_name}/pullrequest/{pr_id}"
    return None


def _normalize_build(b: dict) -> dict:
    definition = b.get("definition") or {}
    links = b.get("_links") or {}
    web_href = (links.get("web") or {}).get("href")
    return {
        "id": b.get("id"),
        "pipeline": definition.get("name"),
        "branch": (b.get("sourceBranch") or "").replace("refs/heads/", ""),
        "status": b.get("status"),       # notStarted | inProgress | completed | cancelling
        "result": b.get("result"),       # succeeded | failed | canceled | partiallySucceeded (only when completed)
        "started": b.get("startTime"),
        "finished": b.get("finishTime"),
        "web_url": web_href,
        "requested_by": (b.get("requestedFor") or {}).get("displayName"),
    }


# Priority (Microsoft.VSTS.Common.Priority) is 1..4 on the Agile/Scrum
# templates. Map to a human urgency label the card + drawer badge on.
_PRIORITY_URGENCY = {1: "critical", 2: "high", 3: "normal", 4: "low"}


def _sprint_leaf(iteration_path: Optional[str]) -> Optional[str]:
    """Last segment of an IterationPath, e.g. 'App\\Sprint 12' -> 'Sprint 12'."""
    if not iteration_path:
        return None
    return iteration_path.replace("/", "\\").split("\\")[-1].strip() or None


def _derive_urgency(fields: dict) -> str:
    """Deterministic urgency from Priority, falling back to Severity, else
    'normal'. No AI - pure field mapping."""
    prio = fields.get("Microsoft.VSTS.Common.Priority")
    if isinstance(prio, (int, float)):
        return _PRIORITY_URGENCY.get(int(prio), "normal")
    severity = (fields.get("Microsoft.VSTS.Common.Severity") or "").lower()
    if "critical" in severity:
        return "critical"
    if "high" in severity:
        return "high"
    if "low" in severity:
        return "low"
    return "normal"


def _normalize_workitem(w: dict, config: ADOConfig) -> dict:
    fields = w.get("fields") or {}
    wid = w.get("id")
    assignee = fields.get("System.AssignedTo") or {}
    creator = fields.get("System.CreatedBy") or {}
    due = (
        fields.get("Microsoft.VSTS.Scheduling.DueDate")
        or fields.get("Microsoft.VSTS.Scheduling.TargetDate")
    )
    return {
        "id": wid,
        "title": fields.get("System.Title"),
        "type": fields.get("System.WorkItemType"),
        "state": fields.get("System.State"),
        "tags": fields.get("System.Tags"),
        "area": fields.get("System.AreaPath"),
        # New for F6 description rendering. ADO returns these as HTML.
        "description": fields.get("System.Description"),
        "acceptance_criteria": fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"),
        # FEAT-002: sprint / due date / urgency for triage at a glance.
        "sprint": _sprint_leaf(fields.get("System.IterationPath")),
        "due_date": due,
        "urgency": _derive_urgency(fields),
        # People + dates
        "assignee": (
            assignee.get("displayName") if isinstance(assignee, dict) else assignee
        ),
        "created_by": (
            creator.get("displayName") if isinstance(creator, dict) else creator
        ),
        "created": fields.get("System.CreatedDate"),
        "changed": fields.get("System.ChangedDate"),
        "web_url": f"{config.base}/_workitems/edit/{wid}",
    }


def _normalize_comment(c: dict) -> dict:
    author = c.get("createdBy") or {}
    return {
        "id": c.get("id"),
        # ADO returns comment text as HTML.
        "text": c.get("text"),
        "author": (author.get("displayName") if isinstance(author, dict) else author),
        "created": c.get("createdDate"),
        "modified": c.get("modifiedDate"),
    }
