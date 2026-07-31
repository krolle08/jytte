# Rule: AI never self-provisions credentials or access

**Scope:** every task in this project, and any task that reaches for access to an external system.

## The hard rule

The AI must **never, under any circumstances, create a credential to give itself access** that a task requires. This covers tokens, PATs, API keys, OAuth app registrations, client secrets, SSH keys, and service principals - and it covers **every channel**: a website UI driven by browser automation, a CLI (`az`, `gh`, `gcloud`, `aws`, ...), or a raw API call. The AI also never decides its own access scopes.

When a task needs access the AI does not already have through human-provisioned config (values in `.env`), the AI **STOPS and asks the human for help**. This overrides any "do not ask" or "just do it" instruction. The AI stops and asks even when told not to.

## Why

An AI going into a system like Azure DevOps, minting its own token, and choosing its own rights breaks every core IT-security principle: separation of duties, least privilege, and auditable human authorization. It can also exceed the (often unknown) extent to which AI use is permitted for a given customer.

## Per-customer permissions

`ai-permissions.json` (project root) is the source of truth for what the AI may do per customer, at an abstract level. Before acting on any customer's systems:

1. Identify which customer the current task belongs to.
2. Read that customer's entry in `ai-permissions.json`.
3. If the customer is not listed, use `default_for_unknown_customer` (read-only, ask before anything else).
4. If `ai_use_policy_known` is `false`, do not act on that customer's systems beyond read-only, and ask first.

The AI never edits `ai-permissions.json` to widen its own permissions - that file records human-granted policy only.

## Deterministic backstop

Behavioral compliance is primary. A PreToolUse hook provides a deterministic backstop that blocks known credential-minting command patterns (see `.claude/settings.json`). The hook cannot see a token created through a browser UI, so it is a safety net, not the whole guarantee - the rule above is.

## Related

- `feedback_no_self_credentials` (auto-memory)
- `feedback_secrets` (never echo secret values)
