#!/usr/bin/env python3
"""PreToolUse guard: deterministic backstop for the "AI never self-provisions
credentials" policy (see .claude/rules/ai-credentials-policy.md).

Reads the PreToolUse event JSON on stdin. If the tool call looks like it would
MINT a credential or self-authorize (create a token / PAT / API key / OAuth
app / client secret / service principal / signing key), it DENIES the call and
tells the model to stop and ask the human.

This is a safety net, not the whole guarantee: a token created by clicking
through a website UI is not a shell command this hook can see. The behavioral
rule in ai-credentials-policy.md is the primary control.

Exit contract: prints a PreToolUse decision object on stdout. "deny" blocks the
call and surfaces the reason to the model.
"""

import json
import re
import sys

# High-signal credential-MINTING patterns. Deliberately narrow to avoid
# blocking read-only auth checks (e.g. `az account get-access-token` uses an
# existing identity; it is not minting a new credential and is not listed).
PATTERNS = [
    r"\bgh\s+auth\s+(login|token|refresh)\b",
    r"\baz\s+ad\s+(app|sp)\s+create\b",
    r"\baz\s+ad\s+(app|sp)\s+credential\b",
    r"\bNew-AzAD(Application|ServicePrincipal|AppCredential|ServicePrincipalCredential)\b",
    r"\baws\s+iam\s+create-(access-key|user|login-profile)\b",
    r"\bgcloud\s+iam\s+service-accounts\s+keys\s+create\b",
    r"\bssh-keygen\b",
    # Azure DevOps PAT lifecycle REST API
    r"_apis/tokens/pats\b",
    # GitHub legacy token API
    r"/authorizations\b.*(curl|http)",
    # Natural-language intent (browser/agent prompts)
    r"\bcreate\b.{0,40}\b(token|personal access token|pat|api key|client secret|app registration)\b",
    r"\bgenerate\b.{0,40}\b(token|personal access token|pat|api key|client secret)\b",
    r"\bnew personal access token\b",
    r"\bregister\b.{0,30}\b(azure ad app|app registration|oauth app)\b",
]

COMPILED = [re.compile(p, re.IGNORECASE) for p in PATTERNS]


def _searchable(event: dict) -> str:
    ti = event.get("tool_input") or {}
    parts = []
    for key in ("command", "prompt", "content", "code", "query", "url"):
        v = ti.get(key)
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        # Fail open on unparseable input - never break normal tool flow.
        return 0

    text = _searchable(event)
    if not text:
        return 0

    for rx in COMPILED:
        if rx.search(text):
            reason = (
                "Blocked by the AI-credentials policy: this looks like it would "
                "create a credential or self-authorize (matched: "
                f"/{rx.pattern}/). The AI must never mint a token/key/app "
                "registration or choose its own scopes. STOP and ask the human "
                "to provision it. See .claude/rules/ai-credentials-policy.md."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }))
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
