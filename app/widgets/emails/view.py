"""Sync view context for the emails card.

Supplies the Dagrofa gate flag. Reading a customer's (Dagrofa) mailbox
touches the ai_use_policy_known=false boundary, so the Dagrofa bucket stays
DARK by default until the operator sets EMAILS_DAGROFA_ENABLED=true (mirrors
the Azure DevOps Dagrofa gate). Even if n8n were to push Dagrofa mail, the
card hides it while the flag is off.
"""

from __future__ import annotations

import os

_FALSEY = {"", "0", "false", "no", "off"}


def context(latest: dict) -> dict:
    raw = os.getenv("EMAILS_DAGROFA_ENABLED", "")
    return {"dagrofa_enabled": raw.strip().lower() not in _FALSEY}
